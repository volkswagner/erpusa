import frappe
from frappe import _
import datetime
import json
from frappe.utils import get_url_to_form, getdate
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
        
        # find the subscription associated
        subscription = frappe.db.exists("Subscription", {"stripe_subscription_id": data.get("subscription")})
        if subscription:
            create_payment_entry_from_stripe_invoice(data, subscription)

def create_payment_entry_from_stripe_invoice(invoice, subscription, reference_date=None, return_invoice_id=False):
    from erpusa.stripe_plus.api.webhook_receiver import create_update_stripe_transaction, get_charge_details, notify_error_to_user_merchant_payment
    api_key = get_api_key_secret(
        payment_gateway=frappe.db.get_value(
            "Subscription",
            subscription,
            "payment_gateway"
        )
    )
    # get charge details
    charge = get_charge_details(
        invoice.get("charge"),
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
            _("The Customer and/or Subscription association failed."),
            frappe.get_traceback()
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
            mp_error_message = _("The Sales Invoice association failed.")
            
            ##  Create a Payment Entry for the oldest sales invoice ##
            if not frappe.db.exists("Payment Entry Reference", { "reference_name":  sales_invoices[0]}):
                # get the Payment Request doc and fetch the cost_center from settings
                pe_doc = get_payment_entry("Sales Invoice", sales_invoices[0], reference_date=reference_date)
                # set the actual amount paid by the user
                for index, reference in enumerate(pe_doc.references):
                    if reference.reference_name == sales_invoices[0]:
                        pe_doc.references[index].allocated_amount = mp_doc.gross_amount

                mp_error_message = _("The Payment Entry creation failed.")

        else:
            pe_doc = frappe.new_doc("Payment Entry")
            pe_doc.party_type = "Customer"
            pe_doc.party = mp_doc.customer
            pe_doc.received_amount = mp_doc.net_amount
            pe_doc.mode_of_payment = pe_doc.mode_of_payment or frappe.get_value("Payment Request", mp_doc.associated_payment_request, "mode_of_payment")
            # set the bank account
            if not pe_doc.bank_account and get_bank_account_for_payment_entry(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, as_dict=False):
                pe_doc.bank_account = get_bank_account_for_payment_entry(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, as_dict=False)
                
            if reference_date:
                pe_doc.reference_date = reference_date

            mp_error_message = _("The Advance Payment Entry creation failed.")

        account = frappe.db.get_value(
            "Payment Gateway Account",
            frappe.db.get_value("Subscription", subscription, "payment_gateway_account"),
            "payment_account"
        )
        
        pe_doc.paid_to = account
        pe_doc.mode_of_payment = frappe.db.get_value("Mode of Payment Account", {"default_account": pe_doc.paid_to}, "parent")
        pe_doc.reference_no = frappe.db.get_value("Stripe Transaction", mp_doc.source, "payment_intent")
        pe_doc.reference_date = getdate()
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

        except Exception as e:
            notify_error_to_user_merchant_payment(
                mp_doc.name,
                _("The Payment Entry creation failed."),
                frappe.get_traceback()
            )
            frappe.log_error(frappe.get_traceback(), _("Error Saving Payment Entry Document"))

        try:
            pe_doc.submit()

        except Exception as e:
            notify_error_to_user_merchant_payment(
                mp_doc.name,
                _("The Payment Entry submission failed."),
                frappe.get_traceback()
            )
            frappe.log_error(frappe.get_traceback(), _("Error Submitting Payment Entry Document"))
                    
        # update Merchant Payment doc
        try:
            mp_doc.associated_payment_entry = pe_doc.name
            mp_doc.save()

        except Exception as e:
            notify_error_to_user_merchant_payment(
                mp_doc.name,
                mp_error_message,
                frappe.get_traceback()
            )
            frappe.log_error(frappe.get_traceback(), _("Error Saving Merchant Payment Document"))

        if not sales_invoices:
            notify_user_advance_payment(mp_doc, pe_doc.reference_no)
            
        if return_invoice_id:
            if sales_invoices:
                return  _("Stripe Transaction ") +\
                    f'<a href="{get_url_to_form("Stripe Transaction", charge.id)}">{charge.id}</a>' +\
                    _(" posted as ") +\
                    f'<a href="{get_url_to_form("Payment Entry", pe_doc.name)}">{pe_doc.name}</a>' +\
                    _(" and paid to ") +\
                    f'<a href="{get_url_to_form("Sales Invoice", sales_invoices[0])}">{sales_invoices[0]}</a>.'
            else:
                return _("Stripe Transaction ") +\
                f'<a href="{get_url_to_form("Stripe Transaction", charge.id)}">{charge.id}</a>' +\
                _(" posted as Advance Payment ") +\
                f'<a href="{get_url_to_form("Payment Entry", pe_doc.name)}">{pe_doc.name}</a>'


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
  stripe_transactions = frappe.db.get_all(
      "Stripe Transaction",
      fields=["name", "payment_intent", "amount", "payment_method_type", "created", "invoice"],
      filters={
        "customer": stripe_customer_id, 
        "invoice": ["in", stripe_invoices],
        "payment_intent": ["not in", frappe.db.get_all(
            "Payment Entry",
            filters={"status": "Submitted"},
            pluck="reference_no"
        )]
        }
    )
  invoice_count = frappe.db.count("Sales Invoice", filters={"status": ["not in", ["Draft", "Paid", "Cancelled"]], "subscription": subscription_name})

  return {
    'unallocated_stripe_transactions': stripe_transactions,
    'invoice_count': invoice_count
  }

@frappe.whitelist()
def allocate_payments(subscription, stripe_transactions, invoice_count, payment_gateway):
  api_key = get_api_key_secret(gateway_controller=frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_controller"))
  stripe_transactions = json.loads(stripe_transactions)
  checked_count = 0

  for st in stripe_transactions:
    if "__checked" in st and st['__checked'] == 1:
        checked_count = checked_count + 1
        stripe_invoice = get_invoice_details(st['invoice'], api_key)

        if stripe_invoice:
            try:
                return_message = create_payment_entry_from_stripe_invoice(stripe_invoice, subscription, st['created'], True)
            except Exception as e:
                frappe.throw(
                    title= _("Alllocation Failed"),
                    msg=str(e)
                )

            frappe.msgprint(
                title=_("Allocation Successful"),
                msg=return_message
            )

    if not checked_count:
        frappe.throw(
            title=_("No Stripe Transactions Selected"),
            msg=_("Select/check at least one Stripe Transaction to allocate.")
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

@frappe.whitelist()
def find_advance_payments(customer):
    return frappe.db.get_all(
        "Payment Entry",
        filters={
            "name": ["not in", frappe.db.get_all(
                "Payment Entry Reference",
                pluck="parent"
            )],
            "reference_no": ["like", "pi%"],
            "party": customer,
            "status": "Submitted"
        },
        pluck="name"
    )
    
@frappe.whitelist()
def fetch_subscription_update_requests(subscription):
    request_list = frappe.db.get_all(
        "Subscription Update Request",
        fields=["name", "request_type", "creation", "additional_information", "new_end_date", "cancellation_date", "resubscription_start_date"],
        filters={
            "subscription": subscription,
            "status": ["not in", ["Approved", "Rejected"]]
        }
    )
    
    subscription_details = frappe.db.get_value("Subscription", subscription, ["end_date", "start_date", "cancelation_date"], as_dict=True)
    
    for index, request in enumerate(request_list):
        request_list[index]["details"] = generate_details(subscription_details["end_date"], request)
        request_list[index]["to_change"] = get_update_request_to_update(subscription, request)
        
        cancellation_date = request.get("cancellation_date")
        if cancellation_date:
            request_list[index]["cancel_today"] = cancellation_date <= subscription_details["end_date"]
            request_list[index]["details"] = cancellation_date
            
            if request_list[index]["cancel_today"]:
                request_list[index]["details"] = str(request_list[index]["details"]) + "(will be cancelled today)"
        
        resubscription_start_date = request.get("resubscription_start_date")
        if resubscription_start_date:
            reference_date = subscription_details["end_date"] or subscription_details["cancelation_date"]
            request_list[index]["resubscribe_today"] = resubscription_start_date <= reference_date
            request_list[index]["details"] = resubscription_start_date
            
            if request_list[index]["resubscribe_today"]:
                request_list[index]["details"] = str(request_list[index]["details"]) + "(will be renewed today)"
    
    return request_list

@frappe.whitelist()
def approve_update_request(update_request_name, notes):
    update_request_doc = frappe.get_doc("Subscription Update Request", update_request_name)
    update_request_doc.status = "Approved"
    update_request_doc.notes = notes
    
    try:
        update_request_doc.save()
    except Exception as e:
        frappe.throw(_("Couldn't Approve the Update Request."))
        
    notify_customer_approval(update_request_doc)
        

def notify_customer_approval(update_request):
    request_type_expanded = {
        "Plan Change": "'s plans were successfully changed.",
        "Plan and End Date Change": "'s plans and subscription end date were successfully changed.",
        "End Date Change": "'s subscription end date was successfully changed.",
        "Cancellation": " was successfully cancelled.",
        "Resubscription": " was successfully renewed."
    }
    recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")
    reference_name= update_request.name + "_approved"
    subscription_name = frappe.db.get_value("Subscription", update_request.subscription, "friendly_name") or update_request.subscription
    message = ("{subscription}{status}").format(subscription=subscription_name, status=request_type_expanded[update_request.request_type])
    
    if update_request.notes:
        notes_list = [f"<li>{note.description}</li>" for note in update_request.notes]
        message = message + "<br/>" + _("The reviewer wrote:") + f"<ol>{notes_list}</ol>"
            
    
    if not frappe.db.exists("Email Queue", {"reference_doctype": "Subscription Update Request", "reference_name": reference_name}):
        frappe.sendmail(
            recipients=recipients.split(),
            subject=_("Your Request for a {type} to Subscription {subscription} Was Approved.").format(type=update_request.request_type,subscription=subscription_name),
            message=message,
            reference_doctype="Subscription Update Request",
            reference_name=reference_name,
            now=True
        )

def generate_details(subscription_end_date, request):
    def formulate_end_date_change_text():
        return "End Date:" + str(subscription_end_date) + " => " + str(request.get("new_end_date"))
    
    def formulate_plan_change_text():
        request_plans = frappe.db.get_all(
            "Update Request Plan",
            filters={
                "parent": request.get("name")
            },
            fields=["plan", "qty", "new_qty"]
        )
        plans_text = []
        for request_plan in request_plans:
            plans_text.append(f'PLAN: {request_plan["plan"]}, CURRENT QTY: {request_plan["qty"]}, NEW QTY: {request_plan["new_qty"]}')
        
        return "<br/>".join(plans_text)
    
    if request.get("request_type") == "Plan Change":
        return formulate_plan_change_text()
    
    if request.get("request_type") == "End Date Change":
        return formulate_end_date_change_text()
    
    if request.get("request_type") == "Plan and End Date Change":
        return f"""
            {formulate_plan_change_text()}
            <br/>
            {formulate_end_date_change_text()}
            """
            
def get_update_request_to_update(subscription, request):
    def get_end_date_changes():
        return {
            "fieldname": "end_date",
            "new_value": request.get("new_end_date")
        }
    
    def get_plan_changes():
        return {
            "fieldname": "plans",
            "new_value": frappe.db.get_all(
                "Update Request Plan",
                filters={
                    "parent": request.get("name")
                },
                fields=["plan_id", "new_qty"]
            )
        }
        
    if request.get("request_type") == "Plan Change":
        return [get_plan_changes()]
    
    if request.get("request_type") == "End Date Change":
        return [get_end_date_changes()]
    
    if request.get("request_type") == "Plan and End Date Change":
        return [
            get_end_date_changes(),
            get_plan_changes()
        ]