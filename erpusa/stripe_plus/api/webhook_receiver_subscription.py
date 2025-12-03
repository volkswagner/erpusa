import frappe
from frappe import _
import datetime
import json
from frappe.utils import get_url_to_form
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret, get_representative_email_address, get_bank_account_for_payment_entry
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import SUBSCRIPTION_STATUS_VERBOSE

def receive_stripe_subscription_events(data, return_invoice_id=False):
    if data.get("object") == "subscription":
        # get metadata to look for associated ERPNext subscription
        metadata = data.get("metadata")
        # check if subscription exists and set the stripe id and status
        if metadata and metadata.get("erp_subscription_name"):
            if not frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_id"):
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
                            customer.append("portal_userss", {
                                "user": user.name
                            })
                        customer.save()
                
            frappe.db.set_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_status", SUBSCRIPTION_STATUS_VERBOSE[data.get("status")])
    
    # make payment entry if subscription was succesfully set up
    if data.get("object") == "invoice" and data.get("status") == "paid" and data.get("subscription"):
        from erpusa.stripe_plus.api.webhook_receiver import create_update_stripe_transaction, get_charge_details, notify_error_to_user_merchant_payment
        
        # find the subscription associated
        subscription = frappe.db.exists("Subscription", {"stripe_subscription_id": data.get("subscription")})
        if subscription:
            api_key = get_api_key_secret(
                payment_gateway=frappe.db.get_value(
                    "Subscription",
                    subscription,
                    "payment_gateway"
                )
            )
            # get charge details
            charge = get_charge_details(
                data.get("charge"),
                api_key
            )
            # update/create Stripe Transaction for the charge data and get the Merchant Payment doc associated
            mp_doc = create_update_stripe_transaction(charge, api_key, return_mp_doc=True) 
            mp_doc.associated_subscription = subscription               
            mp_doc.customer = frappe.db.get_value("Subscription", subscription, "party")

            try:
                mp_doc.save()
            except Exception as e:
                notify_error_to_user_merchant_payment(
                    mp_doc.name,
                    "The Customer and Subscription association failed.",
                    str(e)
                )
                frappe.log_error(frappe.get_traceback(), _("Error Saving Merchant Payment Document"))
            
            user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
            if user_to_authorize:
                frappe.set_user(user_to_authorize)

                # fetch the oldest unpaid sales invoice
                sales_invoices = frappe.db.get_all(
                    "Sales Invoice",
                    filters={"status": ["not in", ["Draft", "Paid", "Cancelled", "Return", "Partly Paid"]], "subscription": subscription},
                    pluck="name",
                    order_by="to_date asc",
                    limit=1
                )

                pe_doc = None
                cost_center = frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_cost_center")
                
                if sales_invoices:
                    # set the customer and associated subscription
                    mp_doc.associated_sales_invoice = sales_invoices[0]
                    mp_error_message = _("The Sales Invoice associated failed.")
                    
                    ##  Create a Payment Entry for the oldest sales invoice ##
                    if not frappe.db.exists("Payment Entry Reference", { "reference_name":  sales_invoices[0]}):
                        # get the Payment Request doc and fetch the cost_center from settings
                        pe_doc = get_payment_entry("Sales Invoice", sales_invoices[0])
                        # set the actual amount paid by the user
                        for index, reference in enumerate(pe_doc.references):
                            if reference.reference_name == sales_invoices[0]:
                                pe_doc.references[index].allocated_amount = mp_doc.gross_amount
                        mp_error_message = _("The Payment Entry creation failed")

                else:
                    pe_doc = frappe.new_doc("Payment Entry")
                    pe_doc.party_type = "Customer"
                    pe_doc.party = mp_doc.customer
                    pe_doc.received_amount = mp_doc.net_amount
                    mp_error_message = _("The Payment Entry creation failed")

                account = frappe.db.get_value(
                    "Payment Gateway Account",
                    frappe.db.get_value("Subscription", subscription, "payment_gateway_account"),
                    "payment_account"
                )
                
                pe_doc.paid_to = account
                pe_doc.mode_of_payment = frappe.db.get_value("Mode of Payment Account", {"default_account": pe_doc.paid_to}, "parent")
                pe_doc.reference_no = frappe.db.get_value("Stripe Transaction", mp_doc.source, "payment_intent")
                pe_doc.reference_date = frappe.utils.getdate()
                pe_doc.paid_amount = mp_doc.net_amount

                # apply Merchant Payment as deduction
                pe_doc.append("deductions", {
                    "account": frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_account"),
                    "cost_center": cost_center,
                    "amount": mp_doc.merchant_fee,
                    "description": mp_doc.name,
                })

                # set the bank account
                if get_bank_account_for_payment_entry(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, as_dict=False):
                    pe_doc.bank_account = get_bank_account_for_payment_entry(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, as_dict=False)

                try:
                    pe_doc.save(ignore_permissions=True)
                    notify_error_to_user_merchant_payment(
                        mp_doc.name,
                        _("The Payment Entry creation failed."),
                        str(e)
                    )

                except Exception as e:
                    frappe.log_error(frappe.get_traceback(), _("Error Saving Payment Entry Document"))

                try:
                    pe_doc.submit()
                    notify_error_to_user_merchant_payment(
                        mp_doc.name,
                        _("The Payment Entry submission failed."),
                        str(e)
                    )

                except Exception as e:
                    frappe.log_error(frappe.get_traceback(), _("Error Submitting Payment Entry Document"))
                            
                # update Merchant Payment doc
                try:
                    mp_doc.associated_payment_entry = pe_doc.name
                    mp_doc.save()

                except Exception as e:
                    notify_error_to_user_merchant_payment(
                        mp_doc.name,
                        mp_error_message,
                        str(e)
                    )
                    frappe.log_error(frappe.get_traceback(), _("Error Saving Merchant Payment Document"))

                if sales_invoices:
                    if return_invoice_id:
                        return sales_invoices[0]

                else:
                    notify_user_advance_payment(mp_doc, pe_doc.reference_no)

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
def allocate_payments(stripe_transactions, invoice_count, payment_gateway):
  api_key = get_api_key_secret(gateway_controller=frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_controller"))
  stripe_transactions = json.loads(stripe_transactions)

#   for index in range(int(invoice_count)):
#     stripe_invoice = get_invoice_details(stripe_transactions[index]['invoice'], api_key)

#     if stripe_invoice:
#       try:
#         sales_invoice = receive_stripe_subscription_events(stripe_invoice)
#       except Exception as e:
#         frappe.throw(_("Alllocation Failed"), str(e))

#       frappe.msgprint(
#         title=_("Allocation Successful"),
#         msg=_("Stripe Transaction {} allocated for {}.").format(stripe_transactions[index]['invoice'], sales_invoice)
#       )

  for st in stripe_transactions:
    stripe_invoice = get_invoice_details(st['invoice'], api_key)

    if stripe_invoice:
      try:
        sales_invoice = receive_stripe_subscription_events(stripe_invoice, True)
      except Exception as e:
        frappe.throw(
           title= _("Alllocation Failed"),
           msg=str(e)
        )

      frappe.msgprint(
        title=_("Allocation Successful"),
        msg=_("Stripe Transaction {} allocated for {}.").format(st['invoice'], sales_invoice)
      )

def notify_user_advance_payment(mp_doc, reference_no):
    subject = _("Advance Payment Received — Subscription {}").format(mp_doc.associated_subscription)
    recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")
    subscription_name = mp_doc.associated_subscription
    subscription_fname = frappe.db.get_value("Subscription", subscription_name, "friendly_name")

    if subscription_fname:
        subscription_name = subscription_name + " / " + subscription_fname
        
    message = frappe.render_template(
        "erpusa/templates/html/advance_payment.html",
        {
            "subscription": subscription_name,
            "customer": mp_doc.customer,
            "amount": mp_doc.net_amount,
            "payment_entry":  mp_doc.associated_payment_entry,
            "merchant_payment": mp_doc.name,
            "subscription_url": get_url_to_form("Subscription", mp_doc.associated_subscription),
            "payment_entry_url": get_url_to_form("Payment Entry", mp_doc.associated_payment_entry),
            "merchant_payment_url": get_url_to_form("Merchant Payment", mp_doc.name)
        },
    )

    reference_name = reference_no + "_advance"

    if not frappe.db.exists("Email Queue", {"reference_name": reference_name}):
        frappe.sendmail(
            recipients=recipients.split(),
            subject=subject,
            message=message,
            reference_name=reference_name,
            now=True
        )
