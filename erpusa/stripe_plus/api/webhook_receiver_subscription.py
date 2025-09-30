import frappe
from frappe import _
import datetime
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

def receive_stripe_subscription_events(data):
    if data.get("object") == "subscription":
        # get metadata to look for associated ERPNext subscription
        metadata = data.get("metadata")
        # check if subscription exists and set the stripe id and status
        if metadata and metadata.get("erp_subscription_name") and not frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_id"):
            frappe.db.set_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_id", data.get("id"))
            frappe.db.set_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_status", SUBSCRIPTION_STATUS_VERBOSE[data.get("status")])
            
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

                if user_to_authorize and user_exists:
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
                        customer.append("portal_user", {
                            "user": user.name
                        })
                    customer.save()
    
    # make payment entry if subscription was succesfully set up
    if data.get("object") == "invoice" and data.get("status") == "paid" and data.get("subscription"):
        from erpusa.stripe_plus.api.webhook_receiver import create_update_stripe_transaction, get_charge_details
        
        # find the subscription associated
        subscription = frappe.db.exists("Subscription", {"stripe_subscription_id": data.get("subscription")})
        api_key = get_api_key_secret(
            payment_gateway=frappe.db.get_value(
                "Subscription",
                frappe.db.exists("Subscription", {"stripe_subscription_id": data.get("subscription")}),
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
        
        user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
        if frappe.db.exists("Subscription", {"stripe_subscription_id": data.get("subscription")}) and user_to_authorize:
            frappe.set_user(user_to_authorize)
            filters = {"status": ["not in", ["Draft", "Paid", "Cancelled"]], "subscription": subscription}
            
            # check if a sales invoice was already generated for the subscription, create if there's none
            if not frappe.db.count("Sales Invoice", filters=filters):
                subscription_doc = frappe.get_doc("Subscription", subscription)
                subscription_doc.current_invoice_start = subscription_doc.current_invoice_start.strftime("%Y-%m-%d")
                subscription_doc.force_fetch_subscription_updates()

            # fetch the oldest unpaid sales invoice
            sales_invoices = frappe.db.get_all(
                "Sales Invoice",
                filters=filters,
                pluck="name",
                order_by="to_date asc",
                limit=1
            )
            
            # set the customer and associated subscription
            mp_doc.customer = frappe.db.get_value("Subscription", subscription, "party")
            mp_doc.associated_subscription = subscription
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

