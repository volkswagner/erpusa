# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


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

		if self.status == "In Review": 
			if not self.reviewer:
				frappe.throw(_("A reviewer needs to be assigned to a request in review."))
	
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
    


