# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
import stripe
import json
from frappe import _
from frappe.model.document import Document
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import METHODS_FULLNAME

DOCTYPE = "Stripe Payment Method Configuration"

class StripePaymentMethodConfiguration(Document):
	def validate(self):
		if not self.payment_methods:
			frappe.throw(_("Payment Methods can't be empty"))

		if self.payment_methods:
			has_dependent_on_card = False
			has_card = False
			for method in self.payment_methods:
				if frappe.db.get_value("Stripe Payment Method", method.payment_method, "payment_method_code") in ["apple_pay", "google_pay"]:
					has_dependent_on_card = True
				if frappe.db.get_value("Stripe Payment Method", method.payment_method, "payment_method_code") == "card":
					has_card = True
			if not has_card and has_dependent_on_card:
				frappe.throw(_("Apple Pay and Google Pay payment methods require Card Payments. Add Card Payments in the payment methods to enable Apple Pay and Google Play."))

	def on_update(self):
		stripe_settings = frappe.get_doc('Stripe Settings', self.stripe_settings)
		stripe.api_key = stripe_settings.get_password('secret_key')

		if not self.stripe_configuration_id:
			try:
				configuration = stripe.PaymentMethodConfiguration.create(
					name=self.configuration_name,
				)
				
				self.db_set("stripe_configuration_id", configuration.id)

			except Exception as e:
				frappe.log_error(f"Stripe Payment Error: {str(e)}", "Stripe API Error")

		self.set_payment_methods(stripe.api_key)
	
	def after_rename(self, doc, old_name, new_name, merge=False):
		stripe.PaymentMethodConfiguration.modify(
			self.stripe_configuration_id,
			name=self.configuration_name,
		)

	def on_trash(self):
		frappe.throw("Configurations can't be deleted. Disable this configuration instead.")

	def get_doc_payment_methods(self):
		dt_pm_table = frappe.qb.DocType("Stripe Payment Method Multiselect Table")
		dt_pm = frappe.qb.DocType("Stripe Payment Method")

		query = (
			frappe.qb.from_(dt_pm)
			.inner_join(dt_pm_table)
			.on(dt_pm_table.payment_method == dt_pm.payment_method_name)
			.where(dt_pm_table.parent == self.configuration_name)
			.select(dt_pm.payment_method_code)
		)
		
		methods = query.run(as_dict=True)

		return [method['payment_method_code'] for method in methods]

	def set_payment_methods(self, api_key):
		# note: commented out payment methods are not enabled because of region limitation
		stripe.api_key = api_key
		list = self.get_doc_payment_methods()

		try:
			stripe.PaymentMethodConfiguration.modify(
				self.stripe_configuration_id,
				active=bool(self.enabled),
				acss_debit={"display_preference": {"preference": "on" if "acss_debit" in list else "off"}},
				affirm={"display_preference": {"preference": "on" if "affirm" in list else "off"}},
				afterpay_clearpay={"display_preference": {"preference": "on" if "afterpay_clearpay" in list else "off"}},
				alipay={"display_preference": {"preference": "on" if "alipay" in list else "off"}},
				# alma={"display_preference": {"preference": "on" if "alma" in list else "off"}},
				apple_pay={"display_preference": {"preference": "on" if "apple_pay" in list else "off"}},
				apple_pay_later={"display_preference": {"preference": "on" if "apple_pay_later" in list else "off"}},
				amazon_pay={"display_preference": {"preference": "on" if "amazon_pay" in list else "off"}},
				# au_becs_debit={"display_preference": {"preference": "on" if "au_becs_debit" in list else "off"}},
				bacs_debit={"display_preference": {"preference": "on" if "bacs_debit" in list else "off"}},
				bancontact={"display_preference": {"preference": "on" if "bancontact" in list else "off"}},
				#billie={"display_preference": {"preference": "on" if "billie" in list else "off"}},
				blik={"display_preference": {"preference": "on" if "blik" in list else "off"}},
				# boleto={"display_preference": {"preference": "on" if "boleto" in list else "off"}},
				card={"display_preference": {"preference": "on" if "card" in list else "off"}},
				cashapp={"display_preference": {"preference": "on" if "cashapp" in list else "off"}},
				# customer_balance={"display_preference": {"preference": "on" if "customer_balance" in list else "off"}},
				eps={"display_preference": {"preference": "on" if "eps" in list else "off"}},
				#fpx={"display_preference": {"preference": "on" if "fpx" in list else "off"}},
				giropay={"display_preference": {"preference": "on" if "giropay" in list else "off"}},
				#grabpay={"display_preference": {"preference": "on" if "grabpay" in list else "off"}},
				google_pay={"display_preference": {"preference": "on" if "google_pay" in list else "off"}},
				ideal={"display_preference": {"preference": "on" if "ideal" in list else "off"}},
				kakao_pay={"display_preference": {"preference": "on" if "kakao_pay" in list else "off"}},
				klarna={"display_preference": {"preference": "on" if "klarna" in list else "off"}},
				#konbini={"display_preference": {"preference": "on" if "konbini" in list else "off"}},
				kr_card={"display_preference": {"preference": "on" if "kr_card" in list else "off"}},
				link={"display_preference": {"preference": "on" if "link" in list else "off"}},
				#mobilepay={"display_preference": {"preference": "on" if "mobilepay" in list else "off"}},
				multibanco={"display_preference": {"preference": "on" if "multibanco" in list else "off"}},
				naver_pay={"display_preference": {"preference": "on" if "naver_pay" in list else "off"}},
				#nz_bank_account={"display_preference": {"preference": "on" if "nz_bank_account" in list else "off"}},
				#oxxo={"display_preference": {"preference": "on" if "oxxo" in list else "off"}},
				p24={"display_preference": {"preference": "on" if "p24" in list else "off"}},
				#pay_by_bank={"display_preference": {"preference": "on" if "pay_by_bank" in list else "off"}},
				payco={"display_preference": {"preference": "on" if "payco" in list else "off"}},
				#paynow={"display_preference": {"preference": "on" if "paynow" in list else "off"}},
				#paypal={"display_preference": {"preference": "on" if "paypal" in list else "off"}},
				pix={"display_preference": {"preference": "on" if "pix" in list else "off"}},
				#promptpay={"display_preference": {"preference": "on" if "promptpay" in list else "off"}},
				#revolut_pay={"display_preference": {"preference": "on" if "revolut_pay" in list else "off"}},
				samsung_pay={"display_preference": {"preference": "on" if "samsung_pay" in list else "off"}},
				#satispay={"display_preference": {"preference": "on" if "satispay" in list else "off"}},
				sepa_debit={"display_preference": {"preference": "on" if "sepa_debit" in list else "off"}},
				sofort={"display_preference": {"preference": "on" if "sofort" in list else "off"}},
				#swish={"display_preference": {"preference": "on" if "swish" in list else "off"}},
				#twint={"display_preference": {"preference": "on" if "twint" in list else "off"}},
				us_bank_account={"display_preference": {"preference": "on" if "us_bank_account" in list else "off"}},
				wechat_pay={"display_preference": {"preference": "on" if "wechat_pay" in list else "off"}},
				zip={"display_preference": {"preference": "on" if "zip" in list else "off"}}
			)

		except Exception as e:
			frappe.log_error(f"Stripe Payment Error: {str(e)}", "Stripe API Error")


@frappe.whitelist()
def fetch_payment_configuration(stripe_settings):
	if not stripe_settings:
		frappe.throw(_("Select a Stripe Settings."))

	stripe.api_key = get_api_key_secret(gateway_controller=stripe_settings)

	try:
		configurations = stripe.PaymentMethodConfiguration.list(limit=100)
		configurations_sanitized = []

		if configurations.data:
			for configuration in configurations.data:
				if not frappe.db.exists(DOCTYPE, {"stripe_configuration_id": configuration.id}):
					configurations_sanitized_item = {
						"stripe_configuration_id": configuration.id,
						"enabled": configuration.active,
						"configuration_name": configuration.name,
						"is_default": configuration.is_default
					}
					configurations_sanitized_payment_methods = []
					configurations_sanitized_payment_methods_code = []

					for method_alias, method in configuration.items():
						if isinstance(method, dict) and method.get("available"):
							method_name = frappe.db.exists("Stripe Payment Method", {"payment_method_code": method_alias})
							if method_name:
								configurations_sanitized_payment_methods_code.append(method_alias)
								configurations_sanitized_payment_methods.append(method_name)

					configurations_sanitized_item["payment_methods"] = configurations_sanitized_payment_methods
					configurations_sanitized_item["payment_methods_code"] = configurations_sanitized_payment_methods_code
					configurations_sanitized_item["payment_methods_joined"] = ", ".join(configurations_sanitized_payment_methods)

					configurations_sanitized.append(configurations_sanitized_item)

			return configurations_sanitized
		
	except Exception as e:
		error = str(e)
		frappe.log_error(f"Stripe API Error: {error}", "Unable to fetch payment configurations.")
		frappe.throw(_("An error occured while fetching payment method configuration. <br><br/>{error}"))

@frappe.whitelist()
def import_configurations(configurations, stripe_settings):
	configurations = json.loads(configurations)
	created_configurations = []

	for configuration in configurations:
		if not frappe.db.exists(DOCTYPE, {"stripe_configuration_id": configuration.get("stripe_configuration_id")}) and \
		configuration.get("__checked"):
			pmc_doc = frappe.new_doc(DOCTYPE)
			pmc_doc.is_user_created = False
			pmc_doc.stripe_settings = stripe_settings
			
			for field, value in configuration.items():
				if pmc_doc.meta.get_field(field) and not field == "payment_methods":
					pmc_doc.set(field, value)

				if field == "payment_methods" and value:
					for method in value:
						pmc_doc.append("payment_methods", {
							"payment_method": method
						})

			try:
				pmc_doc.save()
				created_configurations.append(pmc_doc.configuration_name)

			except Exception as e:
				frappe.log_error(frappe.get_traceback(), _('Error Saving Document'))

	if created_configurations:
		created_configurations_as_html = ""

		for created_configuration in created_configurations:
			created_configurations_as_html = created_configurations_as_html + f"<li>{created_configuration}</li>"

		frappe.msgprint(f"""
			The following payment method configurations was successfully created:
			</br>
			<ul>
				{created_configurations_as_html}
			</ul>
			If you don't see the configurations in the list, refresh the page.
		"""			
		)

@frappe.whitelist()
def resync_payment_method_configuration(configuration_name, stripe_configuration_id, stripe_settings):
	pmc_doc = frappe.get_doc("Stripe Payment Method Configuration", configuration_name)
	stripe.api_key = get_api_key_secret(gateway_controller=stripe_settings)

	try:
		configuration_data = stripe.PaymentMethodConfiguration.retrieve(stripe_configuration_id)
		
	except Exception as e:
		error = str(e)
		frappe.log_error(f"Stripe API Error:", "Unable to fetch payment configurations.")
		frappe.throw(_("An error occured while resyncing with Stripe. <br><br/>{error}"))

	if not pmc_doc.configuration_name == configuration_data.name:
		frappe.rename_doc(DOCTYPE, pmc_doc.configuration_name, configuration_data.name)

	pmc_doc.configuration_name = configuration_data.name
	pmc_doc.enabled = configuration_data.active
	pmc_doc.is_default = configuration_data.is_default
	pmc_doc.payment_methods = []
	payment_methods_count = 0

	for method_alias, method in configuration_data.items():
		if isinstance(method, dict) and method.get("available"):
			method_name = frappe.db.exists("Stripe Payment Method", {"payment_method_code": method_alias})
			pmc_doc.append("payment_methods", {
				"payment_method": method_name 
			})
			payment_methods_count = payment_methods_count + 1

	if payment_methods_count == 0:
		frappe.throw(_("Resyncing failed because the configuration doesn't have any payment method. Modify the configuration in Stripe.com and resync again."))


	try:
		pmc_doc.save()
		frappe.msgprint(_("Resync Successful"))

		return True
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error Saving Document"))
	
	