import frappe
from frappe import _
import datetime
import json
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret, get_representative_email_address, get_bank_account_for_payment_entry
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

SUBSCRIPTION_STATUS_VERBOSE = {
    'incomplete': 'Incomplete',
    'incomplete_expired': 'Incomplete Expired',
    'trialing': 'Trialing',
    'active': 'Active',
    'past_due': 'Past Due',
    'canceled': 'Canceled',
    'unpaid': 'Unpaid',
    'paused': 'Paused'
}

def receive_stripe_subscription_events(data, type, return_docs=False, submit_payment_entries=True):
    if data.get("object") == "subscription":
        # get metadata to look for associated ERPNext subscription
        metadata = data.get("metadata")
        # check if subscription exists and set the stripe id and status
        if metadata and metadata.get("erp_subscription_name") and not frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_id"):
            frappe.db.set_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_id", data.get("id"))
            
            # if stripe is already linked with ERPNext, update the cancellation date if appplicable
            if not frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_status") and frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "end_date"):
                import stripe
                
                stripe.api_key = get_api_key_secret(payment_gateway=frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "payment_gateway"))
                stripe.Subscription.modify(
                    data.get("id"), 
                    cancel_at=int(
                        (datetime.datetime.combine(frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "end_date"), datetime.time()))
                        .timestamp()
                    )
                )
            
             # send welcome email and create user if customer is new
            if not frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_status") and data.get("status") == "active":
                frappe.db.set_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_status", SUBSCRIPTION_STATUS_VERBOSE[data.get("status")])
                user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
                representative = frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "user_account_representative")
                email_address = get_representative_email_address(
                    representative=representative,
                    log_title=f"Failed to send a welcome email for {metadata.get('erp_subscription_name')}.",
                    as_dict=False
                )
                
                if not email_address:
                    return
                
                user_exists = frappe.db.exists("User", email_address)
                
                frappe.sendmail(
                    subject=_("Welcome to {}").format(frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "company")),
                    recipients=[email_address],
                    message=frappe.render_template(
                        "erpusa/templates/html/subscription_welcome.html",
                        {
                            "customer": frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "party"),
                            "subscription": metadata.get("erp_subscription_name"),
                            "user_exists": user_exists
                        },
                    ),
                    now=True,
                    reference_doctype="Subscription",
                    reference_name=f"{metadata.get('erp_subscription_name')}_welcome"
                )

                if user_to_authorize and not user_exists:
                    frappe.set_user(user_to_authorize)
                    user = frappe.new_doc("User")
                    user.email = email_address
                    user.first_name = frappe.db.get_value("Contact", representative, "first_name")
                    user.last_name = frappe.db.get_value("Contact", representative, "last_name")
                    user.save()
                    
                    user.append("roles", {
                        "role": "Customer"
                    })
                    user.save()
                    
                    customer = frappe.get_doc("Customer", frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "party"))
                    if not frappe.db.exists("Portal User", {"parent": customer.name, "user": user.name}):
                        customer.append("portal_users", {
                            "user": user.name
                        })
                    customer.save()
    
    # make payment entry if subscription was succesfully set up
    if data.get("object") == "invoice" and data.get("subscription") and type in ["invoice.finalized", "invoice.created", "invoice.payment_succeeded"]:
        from erpusa.stripe_plus.api.webhook_receiver import create_update_stripe_transaction, get_charge_details
        
        # find the subscription associated and set the filters
        subscription = frappe.db.exists("Subscription", {"stripe_subscription_id": data.get("subscription")})
        filters = {"status": ["not in", ["Draft", "Paid", "Cancelled"]], "subscription": subscription}
        api_key = get_api_key_secret(
            payment_gateway=frappe.db.get_value(
                "Subscription",
                subscription,
                "payment_gateway"
            )
        )

        user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
        if frappe.db.exists("Subscription", {"stripe_subscription_id": data.get("subscription")}) and user_to_authorize:
            frappe.set_user(user_to_authorize)

            if type in ["invoice.finalized", "invoice.created",]:
                # check if a sales invoice was already generated for the subscription, create if there's none
                if not frappe.db.count("Sales Invoice", filters=filters):
                    subscription_doc = frappe.get_doc("Subscription", subscription)
                    subscription_doc.current_invoice_start = subscription_doc.current_invoice_start.strftime("%Y-%m-%d")
                    subscription_doc.force_fetch_subscription_updates()

                sales_invoices = frappe.db.get_all(
                    "Sales Invoice",
                    filters=filters,
                    pluck="name",
                    order_by="to_date asc",
                    limit=1
                )

                if not sales_invoices:
                    raise Exception("An error occured while creating an invoice.")

            if type == "invoice.payment_succeeded":
                charge = None
                # get charge details
                if data.get("charge"):
                    charge = get_charge_details(
                        data.get("charge"),
                        api_key
                    )

                    if not frappe.db.get_value("Subscription", subscription, "card_expiration"):
                        payment_method_details = charge.get("payment_method_details")

                        if payment_method_details and "card" in payment_method_details:
                            card_expiration = f'{str(payment_method_details["card"]["exp_year"])}-{str(payment_method_details["card"]["exp_month"]).zfill(2)}'
                            frappe.db.set_value("Subscription", subscription, "card_expiration", card_expiration)
                
                
                if charge:
                # update/create Stripe Transaction for the charge data and get the Merchant Payment doc associated
                    mp_doc = create_update_stripe_transaction(charge, api_key, return_mp_doc=True)
                    mp_doc.customer = frappe.db.get_value("Subscription", subscription, "party")
                    mp_doc.associated_subscription = subscription

                # fetch the oldest unpaid sales invoice
                sales_invoices = frappe.db.get_all(
                    "Sales Invoice",
                    filters=filters,
                    pluck="name",
                    order_by="to_date asc",
                    limit=1
                )
                
                if sales_invoices:
                    mp_doc.associated_sales_invoice = sales_invoices[0]
                    ##  Create a Payment Entry for the oldest sales invoice ##
                    if not frappe.db.exists("Payment Entry Reference", { "reference_name":  sales_invoices[0]}):
                        # get the Payment Request doc and fetch the cost_center from settings
                        cost_center = frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_cost_center")
                        pe_doc = get_payment_entry("Sales Invoice", sales_invoices[0])
                        # set the actual amount paid by the user
                        for index, reference in enumerate(pe_doc.references):
                            if reference.reference_name == sales_invoices[0]:
                                pe_doc.references[index].allocated_amount = mp_doc.gross_amount
                            
                        pe_doc.reference_no = frappe.db.get_value("Stripe Transaction", mp_doc.source, "payment_intent")
                        pe_doc.paid_amount = mp_doc.net_amount
                        pe_doc.paid_to = frappe.db.get_value("Subscription", subscription, "account")
                        pe_doc.mode_of_payment = frappe.db.get_value("Subscription", subscription, "mode_of_payment")

                        # apply Merchant Payment as deduction
                        pe_doc.append("deductions", {
                            "account": frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_account"),
                            "cost_center": cost_center,
                            "amount": mp_doc.merchant_fee,
                            "description": mp_doc.name,
                        })
                        # set the bank account
                        if get_bank_account_for_payment_entry(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, False, as_dict=False):
                            pe_doc.bank_account = get_bank_account_for_payment_entry(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, False, as_dict=False)

                        if submit_payment_entries:
                            try:
                                pe_doc.save(ignore_permissions=True)
                                pe_doc.submit()
                            except Exception as e:
                                frappe.log_error(frappe.get_traceback(), _("Error Saving Payment Entry Document"))
                            
                        # update Merchant Payment doc
                        try:
                            mp_doc.associated_payment_entry = pe_doc.name
                            mp_doc.save()

                        except Exception as e:
                            frappe.log_error(frappe.get_traceback(), _("Error Saving Merchant Payment Document"))
                else:
                    raise Exception("An error occured while creating a payment entry.")

                if return_docs:
                    {
                        'sales_invoice': sales_invoices[0],
                        'payment_entry': pe_doc.name
                    }

def get_invoice_details(id, api_key):
    import stripe
    # get Invoice object
    if id:
        stripe.api_key = api_key

        try:
            invoice = stripe.Invoice.retrieve(id)
            return invoice
        
        except Exception as e:
            frappe.log_error("Error getting Invoice Details", str(e))
            return None

def list_subscription_invoices(stripe_subscription, api_key):
    import stripe
    # get Invoice object
    if id:
        stripe.api_key = api_key

        try:
            invoices = stripe.Invoice.list(
                subscription=stripe_subscription,
                limit=10
            )
            return invoices
        
        except Exception as e:
            frappe.log_error("Error getting Invoice Details", str(e))
            return None


@frappe.whitelist()
def is_customer_user(representative):
  email_address = get_representative_email_address(
    representative=representative,
    as_dict=False,
  )

  return {
      'user': frappe.db.exists("User", email_address),
      'email_address': email_address
  }

@frappe.whitelist()
def convert_customer_to_user(representative, email_address, customer):
    user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
    if user_to_authorize and email_address:
        try:
            frappe.set_user(user_to_authorize)
            user = frappe.new_doc("User")
            user.email = email_address
            user.first_name = frappe.db.get_value("Contact", representative, "first_name")
            user.last_name = frappe.db.get_value("Contact", representative, "last_name")
            user.save()
            user.append("roles", {
                "role": "Customer"
            })
            user.save()

            customer_doc = frappe.get_doc("Customer", customer)
            if not frappe.db.exists("Portal User", {"parent": customer, "user": user.name}):
                customer_doc.append("portal_users", {
                    "user": user.name
                })
            customer_doc.save()

        except Exception as e:
            frappe.throw(str(e))

        frappe.msgprint(_("Customer was successfully converted to a user."))

@frappe.whitelist()
def find_unallocated_payments(subscription_name, customer_name, stripe_subscription, payment_gateway):
  api_key = get_api_key_secret(gateway_controller=frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_controller"))
  stripe_customer_id = frappe.db.get_value("Customer", customer_name, "stripe_customer_id")
  
  subscription_invoices = list_subscription_invoices(stripe_subscription, api_key)['data']
  stripe_invoices = [invoice["id"] for invoice in subscription_invoices]
  stripe_transactions = frappe.db.get_all("Stripe Transaction", fields=["name", "payment_intent", "amount", "payment_method_type", "created", "invoice"], filters={"customer": stripe_customer_id, "invoice": ["in", stripe_invoices]})
  invoice_count = frappe.db.count("Sales Invoice", filters={"status": ["not in", ["Draft", "Paid", "Cancelled"]], "subscription": subscription_name})
  unallocated_stripe_transactions = []

  for t in stripe_transactions:
    if not frappe.db.exists("Payment Entry", {"reference_no": t.payment_intent}):
      unallocated_stripe_transactions.append(t)

  return {
    'unallocated_stripe_transactions': unallocated_stripe_transactions,
    'invoice_count': invoice_count
  }

@frappe.whitelist()
def allocate_payments(submit_payment_entries, stripe_transactions, invoice_count, payment_gateway):
  api_key = get_api_key_secret(gateway_controller=frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_controller"))
  stripe_transactions = json.loads(stripe_transactions)

  for st in stripe_transactions:
    stripe_invoice = get_invoice_details(st['invoice'], api_key)

    if stripe_invoice:
        try:
            sales_invoice = receive_stripe_subscription_events(stripe_invoice, "invoice.finalized", True)
            si_and_pe = receive_stripe_subscription_events(stripe_invoice, "invoice.payment_succeeded", True, submit_payment_entries)
        except Exception as e:
            frappe.throw(
                title= _("Alllocation Failed"),
                msg=str(e)
            )

        sales_invoice_url = frappe.utils.get_url_to_form("Sales Invoice", si_and_pe['sales_invoice'])
        payment_entry_url = frappe.utils.get_url_to_form("Payment Entry", si_and_pe['payment_entry'])

        frappe.msgprint(
            title=_("Allocation Successful"),
            msg=_('Stripe Transaction {} allocated for <a href="{}">{}</a>. Payment Entry: <a href="{}">{}</a>')
                .format(
                    st['invoice'],
                    sales_invoice_url,
                    si_and_pe['sales_invoice'],
                    payment_entry_url,
                    si_and_pe['payment_entry']
                )
        )

@frappe.whitelist()
def resync_subscription(subscription_name, stripe_subscription_id, payment_gateway):
    import stripe
    api_key = get_api_key_secret(gateway_controller=frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_controller"))

    try:
        subscription = stripe.Subscription.retrieve(
            id=stripe_subscription_id,
            api_key=api_key
        )
    except Exception as e:
        frappe.throw(
            title=_("Resyncing Failed"),
            msg=str(e)
        )

    if subscription:
        frappe.db.set_value("Subscription", subscription_name, "stripe_subscription_status", SUBSCRIPTION_STATUS_VERBOSE[subscription.status])

        frappe.msgprint(
            title=_("Resync Successful"),
            msg=_("Subscription {}'s stripe status changed to {}.").format(subscription_name, SUBSCRIPTION_STATUS_VERBOSE[subscription.status])
        )

