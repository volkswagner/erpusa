import frappe
from frappe import _
import stripe
from frappe.utils import now_datetime

from payments.payment_gateways.doctype.stripe_settings.stripe_settings import get_gateway_controller
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret, get_user_account_representative,  get_representative_email_address

no_cache = 1

expected_keys = (
	"subscription_name",
	"session_id",
)

def get_context(context):
    if not (set(expected_keys) - set(list(frappe.form_dict))):
        subscription = frappe.form_dict["subscription_name"]
        subscription_info = frappe.db.get_value("Subscription", subscription, ["payment_gateway", "friendly_name", "user_account_representative", "payment_url", "stripe_subscription_id"], as_dict=True)
        gateway_controller = get_gateway_controller(
            "Subscription", subscription, subscription_info["payment_gateway"]
        )
        context.subscription_display_name = subscription_info["friendly_name"] or subscription
        context.customer_email = get_representative_email_address(subscription_info["user_account_representative"]),
        context.payment_url = subscription_info["payment_url"]
        context.session_status = update_subscription_payment_method(frappe.form_dict["session_id"], subscription, subscription_info["stripe_subscription_id"], gateway_controller)

    else:
        frappe.redirect_to_message(
            _("Some information is missing"),
            _("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect

@frappe.whitelist(allow_guest=True)
def update_subscription_payment_method(session_id, subscription_name, stripe_subscription_id, gateway_controller):
    stripe.api_key = get_api_key_secret(gateway_controller)
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
    except Exception as error:
        frappe.log_error(frappe.get_traceback(), f"Error Retrieving Session {session_id}")
        error_description = remove_until_char(str(error), ":")
        frappe.enqueue(
            method="erpusa.templates.pages.stripe_plus_subs_change_payment_return.update_subscription_history",
            subscription_name=subscription_name,
            setup_intent_id=setup_intent.id,
            remarks=f"Failed: {error_description}",
            timeout=300
        )
        return error_description
        
    try:
        setup_intent = stripe.SetupIntent.retrieve(session.setup_intent)
        
    except Exception as error:
        frappe.log_error(frappe.get_traceback(), f"Error Retrieving Setup Intent {session.setup_intent}")
        error_description = remove_until_char(str(error), ":")
        update_subscription_history(subscription_name, setup_intent.id, f"Failed: {error_description}")
        return error_description
    
    if setup_intent.status == "succeeded":
        try:
            subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                default_payment_method=setup_intent.payment_method
            )
            
        except Exception as error:
            frappe.log_error(frappe.get_traceback(), f"Error Updating Payment Method for Subscription {subscription_name}")
            error_description = remove_until_char(str(error), ":")
            update_subscription_history(subscription_name, setup_intent.id, f"Failed: {error_description}")
            return error_description
            
        if subscription and subscription.default_payment_method == setup_intent.payment_method:
            update_subscription_history(subscription_name, setup_intent.id, "Successful")
        
        return "succeeded"
    else:
        return setup_intent.status
    
def update_subscription_history(subscription_name, setup_intent_id, remarks):
    frappe.enqueue(
        method="erpusa.templates.pages.stripe_plus_subs_change_payment_return.insert_subscription_update",
        subscription_name=subscription_name,
        setup_intent_id=setup_intent_id,
        remarks=remarks,
        timeout=300
    )

def insert_subscription_update(subscription_name, setup_intent_id, remarks):
    if not frappe.db.exists("Subscription Update", {"reference": setup_intent_id}):
        doc = frappe.get_doc({
            "doctype": "Subscription Update",
            "parenttype": "Subscription",
            "parent": subscription_name,
            "parentfield": "update_history",
            "update_type": "Payment Method Change",
            "update_datetime": now_datetime(),
            "reference": setup_intent_id,
            "remarks": remarks,
            "idx": frappe.db.count("Subscription Update", filters={"parent": subscription_name}) + 1,
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

def remove_until_char(text, char_to_find):
    """
    Removes the substring from the beginning of the text up to and 
    including the first instance of a specified character.
    """
    try:
        # Find the index of the first occurrence of the character
        index = text.find(char_to_find)
        
        # If the character is found, slice the string starting 
        # from the character's index plus one (to exclude the character itself)
        if index != -1:
            return text[index + 1:]
        else:
            # If the character is not found, return the original string
            return text
    except TypeError:
        return "Invalid input: text must be a string."