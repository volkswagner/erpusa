import frappe
from frappe import _

from payments.templates.pages.stripe_checkout import get_api_key


def get_context(context):
    # all these keys exist in form_dict
    if "reference_docname" in frappe.form_dict or "gateway_controller" in frappe.form_dict:
        context.publishable_key = get_api_key(frappe.form_dict.reference_docname, frappe.form_dict.gateway_controller)
        context.to_pay_doctype = frappe.form_dict.to_pay_doctype
        context.to_pay_id = frappe.form_dict.to_pay_id
        context.amount = frappe.form_dict.amount
    else:
        frappe.redirect_to_message(
            _("Some information is missing"),
            _("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect