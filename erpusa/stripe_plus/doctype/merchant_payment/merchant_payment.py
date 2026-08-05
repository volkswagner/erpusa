# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MerchantPayment(Document):
	def validate(self):
		self.created_before = self.created
		
		if self.stripe_status == "Available":
			self.is_available_for_payout = 1

	@frappe.whitelist()
	def retry_payment_entry(self):
		if self.associated_subscription or (self.associated_sales_invoice and frappe.db.get_value("Sales Invoice", self.associated_sales_invoice, "subscription")):
			frappe.throw(_("This function is not designed for subscription payments. Use the 'Look for Unallocated Payments' feature found in the subscription doc instead."))

		from erpusa.stripe_plus.api.webhook_receiver import create_payment_entry

		payment_entry = create_payment_entry(self, True)

		if payment_entry:
			return {
				'success_message': _("Payment Entry created and linked: {payment_entry}").format(payment_entry=f'<a href="${frappe.utils.get_url_to_form("Payment Entry", payment_entry)}">{payment_entry}</a>')
			}
