# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from erpusa.stripe_plus.api.webhook_receiver_subscription import generate_details


class SubscriptionUpdateRequest(Document):
	def validate(self):
		are_plans_changed = False

		plans = self.plans
		for plan in plans:
			frappe.log_error("Plan", str(plan))
			if plan.qty != plan.new_qty:
				are_plans_changed = True
				break

		if are_plans_changed:
			if self.change_end_date:
				self.request_type = "Plan and End Date Change"
				frappe.log_error("Request Type", "Plan and End Date Change")
			else:
				self.request_type = "Plan Change"
				frappe.log_error("Request Type", "Plan Change")
		else:
			if self.change_end_date:
				self.request_type = "End Date Change"
				frappe.log_error("Request Type", "End Date Change")

		if self.status != "Requested": 
			if not self.reviewer:
				frappe.throw(_("A reviewer needs to be assigned to a request in review."))
	
			try:
				if not frappe.db.exists("ToDo", {
					"allocated_to": self.reviewer,
					"reference_type": "Subscription Update Request",
					"reference_name": self.name
				}):
					todo = frappe.get_doc({
						"doctype": "ToDo",
						"allocated_to": self.reviewer,
						"reference_type": "Subscription Update Request",
						"reference_name": self.name,
						"description": "Please review this subscription update request.",
						"status": "Open",
						"priority": "Medium",
						"date": frappe.utils.nowdate(),
						"assigned_by": frappe.session.user
					})
					todo.insert(ignore_permissions=True)
					frappe.db.commit()
			except Exception as e:
				frappe.throw(_("An error occured while assigning the reviewer."))
    
	def after_insert(self):
		self.notify_user()
        
	def notify_user(self):
		recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")
		reference_name= self.name + "_requested"
		if not frappe.db.exists("Email Queue", {"reference_doctype": "Subscription Update Request", "reference_name": reference_name}):
			frappe.sendmail(
				recipients=recipients.split(),
				subject=_("An Update for Subscription {subscription} Was Requested.").format(subscription=self.subscription),
				message=generate_update_request_notification_message(self),
				reference_doctype="Subscription Update Request",
				reference_name=reference_name,
				now=True
			)
    
def generate_update_request_notification_message(request):
    request_dict = request.as_dict()
    details = generate_details(request.subscription, request_dict) if request.request_type not in ["Cancellation", "Resubscription"] else None
    return frappe.render_template(
		"erpusa/templates/html/subscription_update_request.html",
		{
			"request": request,
			"customer": frappe.db.get_value("Subscription", request.subscription, "party"),
			"details":  details
		},
	)
    


