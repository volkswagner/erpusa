# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint
from frappe.model.document import Document
import stripe

METHODS_FULLNAME = {
  "acss_debit": "Pre-authorized Debit Payments",
  "affirm": "Affirm",
  "afterpay_clearpay": "Afterpay / Clearpay",
  "alipay": "Alipay",
  "amazon_pay": "Amazon Pay",
  "apple_pay": "Apple Pay",
  "apple_pay_later": "Apple Pay Later",
  "bacs_debit": "Bacs Direct Debit",
  "bancontact": "Bancontact",
  "blik": "BLIK",
  "card": "Card Payments",
  "cashapp": "Cash App Pay",
  "customer_balance": "Customer Balance",
  "eps": "EPS",
  "giropay": "Giropay",
  "google_pay": "Google Pay",
  "ideal": "iDEAL",
  "kakao_pay": "Kakao Pay",
  "klarna": "Klarna",
  "kr_card": "Korean Cards",
  "link": "Link",
  "multibanco": "Multibanco",
  "naver_pay": "Naver Pay",
  "p24": "Przelewy24",
  "payco": "PAYCO",
  "pix": "Pix",
  "samsung_pay": "Samsung Pay",
  "sepa_debit": "SEPA Direct Debit",
  "sofort": "Sofort",
  "us_bank_account": "ACH Direct Debit",
  "wechat_pay": "WeChat Pay",
  "zip": "Zip"
}

class StripePlusSettings(Document):
  def validate(self):
    if self.signing_secret_list:
      if not self.user_to_authorize or not self.merchant_fee_account or not self.merchant_fee_cost_center:
        frappe.throw(_("Fields User to Authorize, Merchant Fee Account and Cost Centers are empty. Fill them out to enable auto-creation of Payment Entry."))
        
      if frappe.db.get_value("Account", self.merchant_fee_account, "is_group"):
        frappe.throw(_("The selected Merchant Fee Account is a group account and group accounts can't be used in transactions."))

    if self.turn_on_email_notifications:
      if not self.signing_secret_list:
        frappe.throw(_("Can't turn on notifications when signing secret is empty."))
      self.validate_schedule()

      if self.notification_method == "Daily Digest":
        if not self.notification_schedule:
          frappe.throw(_("Notification Schedule can't be empty. Add at least one schedule."))

      if not self.notification_recipients:
        frappe.throw(_("Notifications require a recipient."))

    if self.auto_submit_payment and not self.erp_stripe_accounts:
      frappe.throw(_("An ERP-Stripe Account is needed to automatically submit a payment entry. Link at least one Stripe payout account with an ERP account."))

  def validate_schedule(self):
    import datetime

    if len(self.notification_schedule) >= 2:
      schedule_times = [
          datetime.datetime.strptime(schedule.time, "%H:%M:%S") - datetime.datetime.strptime("00:00:00", "%H:%M:%S")
          for schedule in self.notification_schedule
      ]

      schedule_times.sort()

      all_intervals_within_hour = all(
        (schedule_times[i+1] - schedule_times[i]) < datetime.timedelta(hours=1)
        for i in range(len(schedule_times) - 1)
      )

      if all_intervals_within_hour:
        frappe.throw(_("Schedules can only have an hour (or more) interval between them."))
  
    if len(self.notification_schedule) > 24:
       frappe.throw(_("There can only be 24 timeslots at a time."))

    for schedule in self.notification_schedule:
      if datetime.datetime.strptime(schedule.time, "%H:%M:%S").second != 0 or \
      datetime.datetime.strptime(schedule.time, "%H:%M:%S").microsecond != 0:
        frappe.throw(_("Time must not include seconds or milliseconds."))

@frappe.whitelist()
def is_stripe_plus_applicable(payment_gateway=None):
  if payment_gateway:
    enabled = frappe.db.get_single_value("Stripe Plus Settings", "enable_stripe_plus")

    if payment_gateway:
      is_gateway_stripe = frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_settings") == "Stripe Settings"

    else:
      is_gateway_stripe = False

    return enabled and is_gateway_stripe

  else:
    return False

@frappe.whitelist()
def get_payment_method_code(payment_method_name):
  return frappe.db.get_value("Stripe Payment Method", payment_method_name, "payment_method_code")

def validate_stripe_plus_fields(payment_request, method=None):
  is_stripe_applicable = is_stripe_plus_applicable(payment_request.payment_gateway)
  """ if Stripe Plus is enabled and the payment gateway settings doc is Stripe """

  if is_stripe_applicable:
    if payment_request.party_type == "Customer":
      if payment_request.is_new() and find_customer_configuration(payment_request.party, payment_request.payment_gateway):
        payment_request.payment_method_configuration = find_customer_configuration(payment_request.party, payment_request.payment_gateway)
        payment_request.methods_included = get_pm_configuration_methods(payment_request.payment_method_configuration)
      
      if frappe.db.get_single_value("Stripe Plus Settings", "add_new_checkout_customers"):
        create_stripe_customer(
          payment_request.party,
          stripe_settings=get_gateway_settings_doc(payment_request.payment_gateway),
          show_success_message=0
        )

      else:
        if payment_request.payment_method_configuration:
          pr_payment_methods = frappe.get_all("Stripe Payment Method Multiselect Table", filters={"parent": payment_request.payment_method_configuration}, pluck="payment_method")
          has_customer_balance = False
          
          for method in pr_payment_methods:
            if get_payment_method_code(method) == "customer_balance":
              has_customer_balance = True
              break
            
          if has_customer_balance:
            create_stripe_customer(
              payment_request.party,
              stripe_settings=get_gateway_settings_doc(payment_request.payment_gateway),
              show_success_message=0
            )

    if not payment_request.payment_method_configuration:
      if get_default_payment_configuration_doc():
        payment_request.payment_method_configuration = get_default_payment_configuration_doc()
      payment_request.methods_included = get_default_pm_configuration_methods(payment_request.payment_gateway)

    if payment_request.docstatus == 2:
      payment_request.stripe_intent_id = None

  else:
    return

@frappe.whitelist()
def get_users_with_write_access(doctype, txt, searchfield, start, page_len, filters):
    users = frappe.db.sql("""
        SELECT u.name, u.full_name
        FROM `tabUser` u
        JOIN `tabHas Role` r ON r.parent = u.name
        WHERE r.role = %s
    """, ("Sales Manager",))

    return users

@frappe.whitelist()
def get_gateway_settings_doc(payment_gateway):
	gateway_settings = frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_settings")
	gateway_controller = frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_controller")

	if gateway_settings == "Stripe Settings":
		return frappe.get_doc("Stripe Settings", gateway_controller)
  
	else:
		frappe.throw(_("Not a valid gateway controller."))

def get_api_key_secret(gateway_controller=None, payment_gateway=None):
  if payment_gateway:
    settings = get_gateway_settings_doc(payment_gateway)

  else:
    settings = frappe.get_doc("Stripe Settings", gateway_controller)

  secret_key = settings.get_password("secret_key")

  if cint(frappe.form_dict.get("use_sandbox")):
      secret_key = frappe.conf.sandbox_secret_key

  return secret_key

def get_default_payment_configuration_doc():
  default_pmc = frappe.db.exists("Stripe Payment Method Configuration", {"is_default": True})

  return default_pmc

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_payment_methods(doctype, txt, searchfield, start, page_len, filters):
  return frappe.db.sql(f"""
    SELECT
      name
    FROM
      `tabStripe Payment Method Configuration`
    WHERE
      stripe_settings = "{get_gateway_settings_doc(filters["payment_gateway"]).name}" and enabled = 1
  """
  )

@frappe.whitelist()
def get_default_pm_configuration_methods(payment_gateway):
  default_pmc = get_default_payment_configuration_doc()

  if default_pmc:
     return get_pm_configuration_methods(
        default_pmc
      )
  
  else:
    if payment_gateway:
      stripe.api_key = get_api_key_secret(payment_gateway=payment_gateway)

      configuration_list = stripe.PaymentMethodConfiguration.list()

      if configuration_list.data:
        for configuration in configuration_list.data:
          if configuration.is_default:
            methods = ""
            for method_code, method in configuration.items():
              if isinstance(method, dict) and method["available"]:
                method_name = frappe.db.get_value("Stripe Payment Method", method_code, "payment_method_name")
                methods = methods + f"<br/>{method_name}"
            
            return methods

@frappe.whitelist()
def get_pm_configuration_methods(payment_method_configuration):
  pmc = frappe.get_doc("Stripe Payment Method Configuration", payment_method_configuration)
  methods = []

  for method in pmc.payment_methods:
    methods.append(frappe.db.get_value("Stripe Payment Method", method.payment_method, "payment_method_name"))
        
  return ",<br/>".join(methods)
    

@frappe.whitelist()
def find_customer_configuration(customer, payment_gateway):
  if payment_gateway:
    stripe.api_key = get_api_key_secret(payment_gateway=payment_gateway)
    settings = get_gateway_settings_doc(payment_gateway)

    doctype_stripe_pmc_customer = frappe.qb.DocType('Stripe Payment Method Configuration Customer')

    query = (
      frappe.qb.from_(doctype_stripe_pmc_customer)
      .select(doctype_stripe_pmc_customer.parent.as_('configuration'))
      .where(doctype_stripe_pmc_customer.customer == customer)
      .limit(1)
    )

    result = query.run()

    if result:
      return result[0]
  
@frappe.whitelist()
def create_stripe_customer(customer, stripe_settings=None, show_success_message=0):
  if frappe.db.get_value("Customer", customer, "stripe_customer_id"):
    if show_success_message:
      frappe.throw(_("Customer already added to Stripe with id {stripe_customer}").format(stripe_customer=frappe.db.get_value("Customer", customer, "stripe_customer_id")))
    return
  
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

@frappe.whitelist()
def get_bank_account(payment_type, paid_from, paid_to, trigger_change, as_dict=True):
  account = paid_to if payment_type == "Receive" else paid_from
  bank_account = None

  if account and trigger_change:
      bank_account = frappe.db.get_value("Bank Account", {"account": account}, "name")
      if bank_account:
          bank_account = bank_account

  if as_dict:
    return { "bank_account": bank_account or 0}
  
  else:
     return bank_account