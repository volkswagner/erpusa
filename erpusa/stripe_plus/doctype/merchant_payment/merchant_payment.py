# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class MerchantPayment(Document):
	def validate(self):
		self.created_before = self.created
		
		if self.stripe_status == "Available":
			self.is_available_for_payout = 1
