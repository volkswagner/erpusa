# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

from frappe import _
import frappe
from frappe.utils import cint
from frappe.model.document import Document
import stripe

METHODS_FULLNAME = {
  "acss_debit": "Pre-authorized Debit Payments",
  "affirm": "Affirm",
  "afterpay_clearpay": "Afterpay / Clearpay",
  "alipay": "Alipay",
  "alma": "Alma",
  "amazon_pay": "Amazon Pay",
  "au_becs_debit": "BECS Direct Debit",
  "bacs_debit": "Bacs Direct Debit",
  "bancontact": "Bancontact",
  "billie": "Billie",
  "blik": "BLIK",
  "boleto": "Boleto",
  "card": "Card Payments",
  "card_present": "Stripe Terminal",
  "cashapp": "Cash App Pay",
  "customer_balance": "Bank Transfer",
  "eps": "EPS",
  "fpx": "FPX",
  "giropay": "Giropay",
  "grabpay": "GrabPay",
  "ideal": "iDEAL",
  "interac_present": "Stripe Terminal",
  "kakao_pay": "Kakao Pay",
  "klarna": "Klarna",
  "konbini": "Konbini",
  "kr_card": "Korean Cards",
  "link": "Link",
  "mobilepay": "MobilePay",
  "multibanco": "Multibanco",
  "naver_pay": "Naver Pay",
  "nz_bank_account": "New Zealand BECS Direct Debit",
  "oxxo": "OXXO",
  "p24": "Przelewy24",
  "pay_by_bank": "Pay By Bank",
  "payco": "PAYCO",
  "paynow": "PayNow",
  "paypal": "PayPal",
  "pix": "Pix",
  "promptpay": "PromptPay",
  "revolut_pay": "Revolut Pay",
  "samsung_pay": "Samsung Pay",
  "satispay": "Satispay",
  "sepa_debit": "SEPA Direct Debit",
  "sofort": "Sofort",
  "swish": "Swish",
  "twint": "Twint",
  "us_bank_account": "ACH Direct Debit",
  "wechat_pay": "WeChat Pay",
  "zip": "Zip"
}

class StripePlusSettings(Document):
	def validate(self):
		if self.notification_method == 'Digest' and not self.notification_schedule:
			frappe.throw("Notification Schedule can't be empty. Add at least one schedule.")

@frappe.whitelist()
def get_gateway_settings(payment_gateway):
	gateway_settings = frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_settings")
	gateway_controller = frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_controller")

	if gateway_settings == "Stripe Settings":
		return frappe.get_doc("Stripe Settings", gateway_controller)
	else:
		frappe.throw(_("Not a valid gateway controller."))


def get_api_key_secret(gateway_controller=None, payment_gateway=None):
  if payment_gateway:
    settings = get_gateway_settings(payment_gateway)
  else:
    settings = frappe.get_doc("Stripe Settings", gateway_controller)

  secret_key = settings.get_password("secret_key")
  if cint(frappe.form_dict.get("use_sandbox")):
      secret_key = frappe.conf.sandbox_secret_key

  return secret_key

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_payment_methods(doctype, txt, searchfield, start, page_len, filters):
  return frappe.db.sql(f"""
    SELECT
      name
    FROM
      `tabStripe Payment Method Configuration`
    WHERE
      stripe_settings = "{get_gateway_settings(filters["payment_gateway"]).name}" and enabled = 1
  """
  )

@frappe.whitelist()
def get_default_pm_configuration(payment_gateway):
  if payment_gateway:
    stripe.api_key = get_api_key_secret(payment_gateway=payment_gateway)

    configuration_list = stripe.PaymentMethodConfiguration.list()

    if configuration_list.data:
      for configuration in configuration_list.data:
        if configuration.is_default:
          methods = []
          for method_alias, method in configuration.items():
            if isinstance(method, dict) and method["available"]:
              method_name = METHODS_FULLNAME[method_alias] if method_alias in METHODS_FULLNAME else method_alias.title()
              methods.append(method_name)
          return methods

def validate_stripe_plus_fields(payment_request, method=None):
	enabled = frappe.db.get_single_value("Stripe Plus Settings", "enable_stripe_plus")

	if enabled:
		if not payment_request.use_default_methods and not payment_request.payment_methods:
			frappe.throw(_("Payment Methods is empty. Either use the default methods or choose a payment method configuration."))
	else:
		return

@frappe.whitelist()
def find_customer_configuration(customer):
  pc_customer_list = frappe.qb.DocType('PC Customer List')
  query = (
    frappe.qb.from_(pc_customer_list)
    .select(pc_customer_list.parent.as_('configuration'))
    .where(pc_customer_list.customer == customer)
    .limit(1)
  )
  result = query.run(as_dict=1)

  if result:
    return result[0]

def create_payment_intent(data):
  try:
      intent = stripe.PaymentIntent.create(
          amount=int(float(data.get('amount')) * 100),
          currency='usd',
          payment_method_configuration=data.get('pm_configuration', None),
          metadata={
              'doctype': data.get('doctype'),
              'docname': data.get('docname')
          }
      )
      if frappe.db.exists("Payment Request", data.get('request_name')):
          frappe.db.set_value("Payment Request", data.get('request_name'), "stripe_intent_id", intent['id'])

      return {
          "clientSecret": intent['client_secret'],
          "redirect": ""
      }
  except Exception as e:
      frappe.log_error(f"Stripe Payment Error: {str(e)}", "Stripe API Error")
      return {"error": str(e)}, 403
@frappe.whitelist()
def create_stripe_customer(customer, stripe_settings=None, show_success_message=0):
  if frappe.db.get_value("Customer", customer, "stripe_customer_id"):
    frappe.throw(_("Customer already added to Stripe with id {stripe_customer}").format(stripe_customer=frappe.db.get_value("Customer", customer, "stripe_customer_id")))
  elif not stripe_settings:
    frappe.throw(_("Select a Stripe Settings."))
  else:
    stripe.api_key = get_api_key_secret(gateway_controller=stripe_settings)

    try:
      stripe_customer = stripe.Customer.create(
        name=frappe.db.get_value("Customer", customer, "customer_name"),
        email=frappe.db.get_value("Contact", customer, "email_id"),
      )

      frappe.db.set_value("Customer", customer, "stripe_customer_id", stripe_customer.id)
      if show_success_message:
        frappe.msgprint(_("Customer <b>{customer}</b> was successfully added to Stripe with id <i>{stripe_customer}</i>").format(customer=customer, stripe_customer=stripe_customer.id))
    except Exception as e:
      error = str(e)
      frappe.log_error(f"Stripe Payment Error: {error}", "Stripe API Error")
      frappe.throw(_("An error occured while adding the customer to stripe. <br><br/>{error}"))

# def create_subscription():