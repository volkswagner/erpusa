# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SubscriptionUpdateRequest(Document):
	def validate(self):
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
