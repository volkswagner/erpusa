import frappe
from frappe import _

from payments.templates.pages.stripe_checkout import get_api_key
from payments.payment_gateways.doctype.stripe_settings.stripe_settings import get_gateway_controller
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_customer_contact,  get_representative_email_address
from erpusa.templates.pages.stripe_plus_subs_checkout import get_session_info

no_cache = 1

expected_keys = (
	"session_id",
	"subscription_name",
	"payment_gateway",
)

def get_context(context):
    if not (set(expected_keys) - set(list(frappe.form_dict))):
        gateway_controller = get_gateway_controller(
            "Subscription", frappe.form_dict["subscription_name"], frappe.form_dict["payment_gateway"]
        )
        # context.publishable_key = get_api_key("Subscription", context.gateway_controller)
        context.subscription = frappe.db.get_value("Subscription", frappe.form_dict["subscription_name"], "friendly_name") or frappe.form_dict["subscription_name"]
        context.contact = get_customer_contact(frappe.db.get_value("Subscription", context.subscription, "party"))
        context.customer_email = get_representative_email_address(context.contact),
        context.payment_url = frappe.db.get_value("Subscription", context.subscription, "payment_url")
        context.session_status, context.amount = get_session_info(frappe.form_dict["session_id"], gateway_controller).values()
        
    else:
        frappe.redirect_to_message(
            _("Some information is missing"),
            _("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect