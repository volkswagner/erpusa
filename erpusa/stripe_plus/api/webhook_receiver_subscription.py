import frappe
from frappe import _
import datetime
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret, get_customer_email_address
from erpnext.selling.doctype.customer.customer import get_customer_primary_contact

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
    frappe.enqueue(
        "erpusa.stripe_plus.api.webhook_receiver_subscription.process_stripe_subscription_events",
        queue='short',
        job_name=f"Stripe Event {data.get('id')}",
        data=data
    )

def process_stripe_subscription_events(data):
    if data.get("object") == "subscription":
        metadata = data.get("metadata")
        
        if metadata and metadata.get("erp_subscription_name"):
            frappe.db.set_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_id", data.get("id"))
            
            import stripe
            stripe.api_key = get_api_key_secret(payment_gateway=frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "payment_gateway"))
            stripe.Subscription.modify(
                data.get("id"), 
                cancel_at=int(
                    (datetime.datetime.combine(frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "end_date"), datetime.time()))
                    .timestamp()
                )
            )
            
            if not frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_status") and data.get("status") == "active":
                user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
                customer = frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "party")
                
                email_address = get_customer_email_address(customer,metadata.get("erp_subscription_name"))

                frappe.sendmail(
                    subject=_("Welcome to {}").format(frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "company")),
                    recipients=[email_address],
                    message=frappe.render_template(
                        "erpusa/templates/html/subscription_welcome.html",
                        {
                            "customer": frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "party"),
                        },
                    ),
                    now=True
                )
                frappe.db.set_value("Subscription", metadata.get("erp_subscription_name"), "stripe_subscription_status", SUBSCRIPTION_STATUS_VERBOSE[data.get("status")])

                if user_to_authorize:
                    frappe.set_user(user_to_authorize)
                    user = frappe.new_doc("User")
                    user.email = email_address
                    user.first_name = frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "user_first_name") or frappe.db.get_value("Customer", customer, "customer_name")
                    user.last_name = frappe.db.get_value("Subscription", metadata.get("erp_subscription_name"), "user_last_name")
                    user.save()
                    
                    user.append("roles", {
                        "role": "Customer"
                    })

                    user.save()
            