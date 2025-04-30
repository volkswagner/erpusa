# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
import stripe
from frappe.model.document import Document


class StripePaymentMethodConfiguration(Document):
	def before_save(self):
		if not self.stripe_configuration_id and self.enabled:
			stripe_settings = frappe.get_doc('Stripe Settings', self.stripe_settings)
			stripe.api_key = stripe_settings.get_password('secret_key')

			try:
				configuration = stripe.PaymentMethodConfiguration.create(
					name=self.configuration_name,
					us_bank_account={"display_preference": {"preference": "on" if self.card else "off"}},
					card={"display_preference": {"preference": "on" if self.card else "off"}}
				)

				self.stripe_configuration_id = configuration.id

			except Exception as e:
				frappe.log_error(f"Stripe Payment Error: {str(e)}", "Stripe API Error")
		else:
			doc_has_changed = self.check_if_doc_changed()
			if doc_has_changed:
				self.update_configuration()
	
	def after_rename(self, doc, old_name, new_name, merge=False):
		self.update_configuration()

	def on_trash(self):
		frappe.throw("Configurations can't be deleted. Disable this configuration instead.")

	def check_if_doc_changed(self):
		old_doc = self.get_doc_before_save()

		if not old_doc:
			return False

		if old_doc.stripe_settings != self.stripe_settings:
			frappe.throw("The Stripe Settings can't be changed.")

		if old_doc.enabled != self.enabled:
			return True

		if old_doc.card != self.card:
			return True
	
		if old_doc.ach_debit_card != self.ach_debit_card:
			return True
		
		return False

	def update_configuration(self):
		stripe_settings = frappe.get_doc('Stripe Settings', self.stripe_settings)
		stripe.api_key = stripe_settings.get_password('secret_key')

		try:
			stripe.PaymentMethodConfiguration.modify(
				self.stripe_configuration_id,
				name=self.configuration_name,
				active=bool(self.enabled),
				us_bank_account={"display_preference": {"preference": "on" if self.card else "off"}},
				card={"display_preference": {"preference": "on" if self.card else "off"}}
			)

		except Exception as e:
			frappe.log_error(f"Stripe Payment Error: {str(e)}", "Stripe API Error")