import frappe
from frappe import _

def get_context(context):
	context.data = frappe.form_dict
	context.customer = frappe.db.exists("Customer", {"user": frappe.session.user})
 
	if context.data and context.data.susbcription and \
    frappe.db.get_value("Subscription", context.data["subscription"], "party") != context.customer:
		frappe.redirect_to_message(
            _("You are not allowed to access this page"),
            _("The subscription you're attempting to update belongs to another user."),
        )
		frappe.local.flags.redirect_location = frappe.local.response.location
		raise frappe.Redirect