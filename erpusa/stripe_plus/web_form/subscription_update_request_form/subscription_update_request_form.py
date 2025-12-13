import frappe
from frappe import _

def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(_("You must be logged in to access this page."), frappe.PermissionError)
  
	context.customer = frappe.db.exists("Customer", {"user": frappe.session.user})
	context.data = frappe.form_dict
	context.end_date = frappe.db.get_value("Subscription", context.data.get("subscription"), "end_date")
	context.is_new = context.data.get("is_new")
	context.is_cancellation = context.data.get("cancellation")
	context.is_resubscription = context.data.get("resubscription")

	if context.is_new:
		if not context.data.get("subscription"):
			frappe.redirect_to_message(
				_("Some information is missing"),
				_("Go back to the Subscriptions {link} in the portal home and create a new request.").format(link='<a href="/subscriptions?status=Active">tab</a>'),
			)
			frappe.local.flags.redirect_location = frappe.local.response.location
			raise frappe.Redirect

		if not context.customer or frappe.db.get_value("Subscription", context.data.get("subscription"), "party") != context.customer:
			frappe.redirect_to_message(
				_("You are not allowed to access this page"),
				_("The subscription you're trying to update belongs to another user."),
			)
			frappe.local.flags.redirect_location = frappe.local.response.location
			raise frappe.Redirect

		if frappe.db.get_value("Subscription", context.data.get("subscription"), "status") in ["Cancelled", "Completed"]:
			if context.is_cancellation:
				frappe.redirect_to_message(
					_("Request not allowed"),
					_("Cancellation only applies to Active Subscriptions."),
				)
				frappe.local.flags.redirect_location = frappe.local.response.location
				raise frappe.Redirect

			if not context.is_resubscription:
				frappe.redirect_to_message(
					_("Request not allowed"),
					_("Changes can only be requested for Active Subscriptions."),
				)
				frappe.local.flags.redirect_location = frappe.local.response.location
				raise frappe.Redirect

		if not frappe.db.get_value("Subscription", context.data.get("subscription"), "status") in ["Cancelled", "Completed"] and context.is_resubscription:
			frappe.redirect_to_message(
				_("Request not allowed"),
				_("Resubscription only applies to Cancelled or Completed Subscriptions."),
			)
			frappe.local.flags.redirect_location = frappe.local.response.location
			raise frappe.Redirect
