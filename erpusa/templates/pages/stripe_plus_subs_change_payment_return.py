import frappe
from frappe import _
import stripe
from frappe.utils import get_datetime, now_datetime

from payments.payment_gateways.doctype.stripe_settings.stripe_settings import get_gateway_controller
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret, get_customer_contact,  get_representative_email_address

no_cache = 1

expected_keys = (
	"subscription_name",
	"payment_gateway",
	"session_id",
)

def get_context(context):
    if not (set(expected_keys) - set(list(frappe.form_dict))):
        gateway_controller = get_gateway_controller(
            "Subscription", frappe.form_dict["subscription_name"], frappe.form_dict["payment_gateway"]
        )
        # context.publishable_key = get_api_key("Subscription", context.gateway_controller)
        subscription = frappe.form_dict["subscription_name"]
        contact = get_customer_contact(frappe.db.get_value("Subscription", subscription, "party"))
        context.customer_email = get_representative_email_address(contact),
        context.payment_url = frappe.db.get_value("Subscription", subscription, "payment_url")
        context.session_status = update_subscription_payment_method(frappe.form_dict["session_id"], frappe.form_dict["subscription_name"], gateway_controller)
        
    else:
        frappe.redirect_to_message(
            _("Some information is missing"),
            _("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect

@frappe.whitelist(allow_guest=True)
def update_subscription_payment_method(session_id, subscription_name, gateway_controller):
    stripe.api_key = get_api_key_secret(gateway_controller)
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
    except Exception as error:
        frappe.log_error(f"Error Retrieving Session {session_id}", str(error))
        
    try:
        setup_intent = stripe.SetupIntent.retrieve(session.setup_intent)
        
    except Exception as error:
        frappe.log_error(f"Error Retrieving Setup Intent {session.setup_intent}", str(error))
    
    if setup_intent.status == "succeeded":
        try:
            subscription = stripe.Subscription.modify(
                setup_intent.metadata.stripe_subscription_id,
                default_payment_method=setup_intent.payment_method
            )
            
        except Exception as error:
            frappe.log_error(f"Error Updating Payment Method for Subscription {setup_intent.metadata.stripe_subscription_id}", str(error))
            
        if subscription and subscription.default_payment_method == setup_intent.payment_method:
            frappe.enqueue(
                method="erpusa.templates.pages.stripe_plus_subs_change_payment_return.update_subscription_history",
                subscription_name=subscription_name,
                setup_intent_id=setup_intent.id,
                job_name=setup_intent.id,
                timeout=300
            )
        
        return "succeeded"
    else:
        return setup_intent.status
    
def update_subscription_history(subscription_name, setup_intent_id):
    if not frappe.db.exists("Subscription Update", {"reference": setup_intent_id}):
        doc = frappe.get_doc({
            "doctype": "Subscription Update",
            "parenttype": "Subscription",
            "parent": subscription_name,
            "parentfield": "update_history",
            "update_type": "Payment Method Change",
            "update_datetime": now_datetime(),
            "reference": setup_intent_id,
            "idx": frappe.db.count("Subscription Update", filters={"parent": subscription_name}) + 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()