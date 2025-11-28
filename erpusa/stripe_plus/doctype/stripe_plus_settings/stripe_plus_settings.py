# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from urllib.parse import urlencode
from frappe.model.document import Document
import stripe
from jinja2 import Template
import re
from frappe.utils import cint
from erpnext.selling.doctype.customer.customer import get_customer_primary_contact

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

SUBSCRIPTION_STATUS_VERBOSE = {
    'incomplete': 'Incomplete',
    'incomplete_expired': 'Incomplete Expired',
    'trialing': 'Trialing',
    'active': 'Active',
    'past_due': 'Past Due',
    'canceled': 'Canceled',
    'unpaid': 'Unpaid',
    'paused': 'Paused'
}

class StripePlusSettings(Document):
  def validate(self):
    if self.signing_secret_list:
      if not self.user_to_authorize or not self.merchant_fee_account or not self.merchant_fee_cost_center:
        frappe.throw(_("Fields User to Authorize, Merchant Fee Account and Cost Centers are empty. Fill them out to enable auto-creation of Payment Entry."))

    if self.turn_on_email_notifications:
      if not self.signing_secret_list:
        frappe.throw(_("Can't turn on notifications when signing secret is empty."))

      self.validate_schedule()

      if self.notification_method == "Daily Digest" and not self.notification_schedule:
        frappe.throw(_("Notification Schedule can't be empty. Add at least one schedule."))

      if not self.notification_recipients:
        frappe.throw(_("Notifications require a recipient."))

    if self.auto_submit_journal and not self.erp_stripe_accounts:
      frappe.throw(_("An ERP-Stripe Account is needed to automatically submit a payout journal entry. Link at least one Stripe payout account with an ERP account."))

    if self.erp_stripe_accounts:
      self.validate_erp_stripe_account()


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

  def validate_erp_stripe_account(self):
    default_count = 0

    for erp_stripe_account in self.erp_stripe_accounts:
      if erp_stripe_account.is_default_payout_account:
        default_count = default_count + 1

      if default_count > 1:
        frappe.throw(_("There can only be one default ERP-Stripe account link."))

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
          show_success_message=frappe.db.get_single_value("Stripe Plus Settings", "show_error_message")
        )

      if not payment_request.payment_method_configuration:
        if get_default_payment_configuration_doc():
          payment_request.payment_method_configuration = get_default_payment_configuration_doc()
          
        payment_request.methods_included = get_default_pm_configuration_methods(payment_request.payment_gateway)

    if payment_request.docstatus == 2:
      payment_request.stripe_intent_id = None

  else:
    return
  
def validate_auto_repeat_stripe_plus_fields(auto_repeat, method=None):
  if auto_repeat.send_payment_request_instead:
    if auto_repeat.reference_doctype in ["Sales Order", "Sales Invoice"] and (not auto_repeat.mode_of_payment or not auto_repeat.payment_gateway_account):
      frappe.throw(_("Select a Mode of Payment or a Payment Gateway Account"))
    if not auto_repeat.submit_on_creation:
      frappe.throw(_("Enable 'Submit on creation' to allow Payment Request."))
    if not auto_repeat.notify_by_email:
      frappe.throw(_("Enable 'Notify by email' to allow Payment Request."))
      
def update_stripe_customer_info(contact, method=None):
  if contact.links and \
    (contact.has_value_changed("email_id") or \
    contact.has_value_changed("is_billing_contact") or \
    contact.has_value_changed("is_primary_contact")):

    for link in contact.links:
      if link.link_doctype == "Customer" and frappe.db.get_value("Customer", link.link_name, "stripe_customer_id"):
        update_stripe_customer(
          frappe.db.get_value("Customer", link.link_name, "stripe_customer_id"),
          frappe.db.get_value("Customer", link.link_name, "stripe_settings"),
          get_representative_email_address(contact.name, as_dict=False, log_title=None, email_id_override=contact.email_id) or ""
        )

@frappe.whitelist()
def get_customer_contact(customer):
  for contact_type in ("is_billing_contact", "is_primary_contact"):
    contact_list = get_customer_primary_contact(
      "Customer", "", "name", 0, 11, {"customer": customer, contact_type: 1}
    )
    
    if contact_list:
      return contact_list[0][0]
      
  return None

def get_representative_email_address(representative, as_dict=True, log_title=None, email_id_override=None):
  # email_id_override is for when the old value is needed
  email_address = email_id_override or frappe.db.get_value("Contact", representative, "email_id", as_dict=as_dict)
  
  if not email_address:
      email_list = frappe.db.get_all("Contact Email", filters={"parent": representative}, pluck="email_id")
      
      if email_list:
          email_address = email_list[0]
      elif log_title:
          frappe.log_error(log_title, f"No email address was found for its representative {representative}.")

  return email_address
  
def validate_subscription_stripe_plus_fields(subscription, method=None):
  if subscription.autocharge_with_stripe:
    if not frappe.db.get_single_value("Stripe Plus Settings", "default_subscription_update_recipient"):
      frappe.throw(_("A default recipient for Subscription Update Emails is needed for autocharging with Stripe. Open Stripe Plus Settings and go to Subscription Tab to set the default recipient."))
    
    if not subscription.stripe_subscription_id:
      if not subscription.user_account_representative:
        frappe.throw(_("User Account Representative is required to enable autocharging through Stripe."))
      
      if not frappe.db.count("Contact Email", filters={"parent": subscription.user_account_representative}):
        frappe.throw(_("The selected User Account Representative doesn't have an email. Set an email address for the contact or choose a different one."))
        
      if not subscription.generate_invoice_at == "Beginning of the current subscription period":
        subscription.generate_invoice_at = "Beginning of the current subscription period"
        frappe.msgprint(_("Field generate_invoice_at was changed to <b>Beginning of the current subscription period</b> to allow auto-charging with Stripe."))

      if not subscription.payment_gateway_account:
        frappe.throw(_("Payment Gateway Account is required to enable autocharging through Stripe."))

    if subscription.email_queue and not frappe.db.exists("Email Queue", subscription.email_queue):
      subscription.email_queue = None

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
	gateway_controller = frappe.db.get_value("Payment Gateway", payment_gateway, "gateway_controller")

	return frappe.get_doc("Stripe Settings", gateway_controller)

def get_api_key_secret(gateway_controller=None, payment_gateway=None):
  if payment_gateway:
    settings = get_gateway_settings_doc(payment_gateway)

  if gateway_controller:
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
    return get_pm_configuration_methods(default_pmc)
  
  else:
    if payment_gateway:
      stripe.api_key = get_api_key_secret(payment_gateway=payment_gateway)

      configuration_list = stripe.PaymentMethodConfiguration.list(limit=100)

      if configuration_list.data:
        for configuration in configuration_list.data:
          if configuration.is_default:
            methods = []
            
            for method_code, method in configuration.items():
              if isinstance(method, dict) and method["available"]:
                method_name = frappe.db.exists("Stripe Payment Method", {"payment_method_code": method_code})
                methods.append(method_name)
            
            if not methods:
              frappe.throw(_("The default payment method configuration in your Stripe account has no payment methods. To proceed, set up at least one payment method through Stripe.com dashboard."))
              
            return ",<br/>".join(methods)

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
  
  if not stripe_settings:
    frappe.throw(_("Select a Stripe Settings."))

  stripe.api_key = get_api_key_secret(gateway_controller=stripe_settings)

  try:
    matching_customer_list = stripe.Customer.search(query=f"metadata['erp_customer_name']:'{customer}'")

  except Exception as e:
    frappe.log_error(f"Error Fetching Customers: ", str(e))
    if show_success_message:
      frappe.throw(_("An error occured while looking for customer in stripe.com. <br><br/>{}").format(str(e)))

  if matching_customer_list and matching_customer_list.get("data"):
    if show_success_message:
      frappe.throw(_("Can't add customer to Stripe. Customer has already been added to Stripe."))
    return

  customer_contact = get_customer_contact(customer)
  if not customer_contact and show_success_message:
    frappe.throw(_("A preferred contact information does not exist for {}.").format(customer))
    
  customer_email_address = get_representative_email_address(customer_contact, as_dict=False)
  if not customer_email_address and show_success_message:
    frappe.throw(_("{} doesn't have an email address.").format(customer_contact))
    
  try:
    stripe_customer = stripe.Customer.create(
      name=frappe.db.get_value("Customer", customer, "customer_name"),
      email=customer_email_address,
      metadata={
        "erp_customer_name": customer
      }
    )

    frappe.db.set_value("Customer", customer, "stripe_customer_id", stripe_customer.id)
    frappe.db.set_value("Customer", customer, "stripe_settings", stripe_settings)
    if show_success_message:
      frappe.msgprint(_("Customer <b>{customer}</b> was successfully added to Stripe with id <i>{stripe_customer}</i>").format(customer=customer, stripe_customer=stripe_customer.id))

  except Exception as e:
    frappe.log_error(f"Error Adding Customer to Stripe: ", str(e))
    if show_success_message:
      frappe.throw(_("An error occured while adding the customer to stripe. <br><br/>{}").format(str(e)))
      
def update_stripe_customer(stripe_customer_id, stripe_settings, email_address):
  if stripe_settings:
    stripe.api_key = get_api_key_secret(gateway_controller=stripe_settings)

    try:
      stripe_customer = stripe.Customer.retrieve(stripe_customer_id)

    except Exception as e:
      frappe.log_error(f"Can't find customer in stripe.com", str(e))
      
    try:
      stripe_customer = stripe.Customer.modify(
        stripe_customer_id,
        email=email_address
      )

    except Exception as e:
      frappe.log_error(f"Can't update customer in stripe.com", str(e))

@frappe.whitelist()
def get_bank_account_for_payment_entry(payment_type, paid_from, paid_to, trigger_change, as_dict=True):
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
   
@frappe.whitelist()
def get_bank_account_for_payment_request(mode_of_payment, reference_doctype=None, reference_docname=None, company=None):
  bank_account = None
  payment_gateway_account = None
  
  if not company:
    company = frappe.db.get_value(reference_doctype, reference_docname, "company")
  
  if mode_of_payment and company:
    account = frappe.db.get_value("Mode of Payment Account", {"parent": mode_of_payment, "company": company}, "default_account")
    
    if account:
      bank_account = frappe.db.get_value("Bank Account", {"account": account}, "name")
      payment_gateway_account = frappe.db.get_value("Payment Gateway Account", {"payment_account": account}, "name")
      
  return {
    "bank_account": bank_account,
    "payment_gateway_account": payment_gateway_account
  }
  
@frappe.whitelist()
def get_customer_funding_instructions(gateway_controller, customer):
  stripe.api_key = get_api_key_secret(gateway_controller=gateway_controller)

  try:
    customer_funding_instructions = stripe.Customer.create_funding_instructions(
      customer,
      funding_type="bank_transfer",
      bank_transfer={"type": "us_bank_transfer"},
      currency="usd",
    )

  except Exception as e:
    error = str(e)
    frappe.log_error(f"Error Fetching Customer's Funding Instructions: ", str(error))

  if customer_funding_instructions:
    bank_transfer = customer_funding_instructions.get("bank_transfer")

    return bank_transfer.financial_addresses

def create_stripe_product(item, stripe_settings=None):
  if not frappe.db.get_value("Item", item, "stripe_product_id"):
    stripe.api_key = get_api_key_secret(gateway_controller=stripe_settings)
    stripe_product_id = None
    
    try:
      matching_product_list = stripe.Product.search(query=f"metadata['erp_item_name']:'{item}'")

    except Exception as e:
      matching_product_list = None
      error = str(e)
      frappe.log_error(f"Error Fetching Price: ", str(error))
    
    if matching_product_list and matching_product_list.get("data"):
      stripe_product_id = matching_product_list["data"][0]["id"]
        
    else:
      try:
        stripe_product = stripe.Product.create(
          active=True,
          name=frappe.db.get_value("Item", item, "item_name"),
          description=frappe.db.get_value("Item", item, "description"),
          metadata={
            'erp_item_name': item
          }
        )
        
        stripe_product_id = stripe_product.id

      except Exception as e:
        error = str(e)
        frappe.log_error(f"Error Adding Product to Stripe: ", str(error))
        frappe.throw(_("An error occured while adding the product to stripe. <br><br/>{0}").format(error))
        
    if stripe_product_id:
      frappe.db.set_value("Item", item, "stripe_product_id", stripe_product_id)

def create_stripe_price(subscription_plan, item, stripe_product_id, stripe_settings=None):
  stripe.api_key = get_api_key_secret(gateway_controller=stripe_settings)
  stripe_price_id = None
  
  try:
    matching_price_list = stripe.Price.search(query=f"metadata['erp_subscription_plan_name']:'{subscription_plan}'")

  except Exception as e:
    matching_price_list = None
    error = str(e)
    frappe.log_error(f"Error Fetching Price: ", str(error))
  
  if matching_price_list and matching_price_list.get("data"):
    stripe_price_id = matching_price_list["data"][0]["id"]
    
  else:
    if not frappe.db.get_value("Subscription Plan", subscription_plan, "cost"):
      price = frappe.db.get_value(
        "Item Price",
        {
            "item_code": item,
            "price_list": frappe.db.get_value("Subscription Plan", subscription_plan, "price_list")
        },
        "price_list_rate"
      ) * 100
    
    else:
      price = frappe.db.get_value("Subscription Plan", subscription_plan, "cost") * 100
      
    try:
      stripe_price = stripe.Price.create(
        active=True,
        unit_amount=int(price),
        currency=frappe.db.get_value("Subscription Plan", subscription_plan, "currency").lower(),
        product=stripe_product_id,
        nickname=subscription_plan,
        recurring={
          "interval": frappe.db.get_value("Subscription Plan", subscription_plan, "billing_interval").lower(),
          "interval_count": frappe.db.get_value("Subscription Plan", subscription_plan, "billing_interval_count")
        },
        metadata={
          "erp_subscription_plan_name": subscription_plan
        }
      )
      
      stripe_price_id = stripe_price.id

    except Exception as e:
      error = str(e)
      frappe.log_error(f"Error Adding Price to Stripe: ", str(error))
      frappe.throw(_("An error occured while adding the price to stripe. <br><br/>{error}"))
      
  if stripe_price_id:
    frappe.db.set_value("Subscription Plan", subscription_plan, "stripe_price_id", stripe_price_id)

@frappe.whitelist()
def calculate_subscription_plan_total(subscription, is_doc=True, include_billing=True, include_grand_total=True):
  if isinstance(is_doc, str):
      is_doc = is_doc.lower() == "true"
  if isinstance(include_billing, str):
      include_billing = include_billing.lower() == "true"
  if isinstance(include_grand_total, str):
      include_grand_total = include_grand_total.lower() == "true"
      
  if not is_doc:
    subscription = frappe.get_doc("Subscription", subscription)
    
  subscription_plan_list = []
  subscription_plan_grand_total = 0.00
  for subscription_plan in subscription.plans:
    if not frappe.db.get_value("Subscription Plan", subscription_plan.plan, "cost"):
      price = frappe.db.get_value(
        "Item Price",
        {
            "item_code": frappe.db.get_value("Subscription Plan", subscription_plan.plan, "item"),
            "price_list": frappe.db.get_value("Subscription Plan", subscription_plan.plan, "price_list")
        },
        "price_list_rate"
      )
    
    else:
      price = frappe.db.get_value("Subscription Plan", subscription_plan.plan, "cost")
    
    temp_plan = {
      "plan": subscription_plan.plan,
      "qty": subscription_plan.qty,
      "price": price,
      "amount": subscription_plan.qty * (price or 0)
    }
    
    if include_billing:
      temp_plan["billing_interval"] = frappe.db.get_value("Subscription Plan", subscription_plan.plan, "billing_interval")
      temp_plan["billing_interval_count"] = frappe.db.get_value("Subscription Plan", subscription_plan.plan, "billing_interval_count")
      
    subscription_plan_list.append(frappe._dict(temp_plan))
  
  subscription_plan_grand_total = subscription_plan_grand_total + (subscription_plan.qty * price)
  
  if include_grand_total:
    return subscription_plan_list, subscription_plan_grand_total
  
  return subscription_plan_list

def setup_stripe_subscription_registration(subscription, method=None):
  if subscription.autocharge_with_stripe and not subscription.email_queue:
    stripe_settings = get_gateway_settings_doc(subscription.payment_gateway)
    if not subscription.stripe_subscription_id:
      stripe_customer_id = frappe.db.get_value("Customer", subscription.party, "stripe_customer_id")
      
      if not stripe_customer_id:
        create_stripe_customer(customer=subscription.party, stripe_settings=stripe_settings)
        
      stripe_customer_id = frappe.db.get_value("Customer", subscription.party, "stripe_customer_id")
      
      for plan in subscription.plans:
        plan_item = frappe.db.get_value("Subscription Plan", plan.plan, "item")
        create_stripe_product(plan_item, stripe_settings)
        stripe_product_id = frappe.db.get_value("Item", plan_item, "stripe_product_id")
        
        if stripe_product_id:
          create_stripe_price(plan.plan, plan_item, stripe_product_id, stripe_settings)
      
      if not frappe.db.exists("Email Queue", {"reference_doctype": "Subscription", "reference_name": subscription.name}):
        send_subscription_email_to_user(subscription)

  frappe.log_error(str(subscription.email_queue))
  if subscription.email_queue and not frappe.db.exists("Email Queue", subscription.email_queue):
    subscription.email_queue = None

def send_subscription_email_to_user(subscription):
  params = {
    'subscription_name': subscription.name,
    'customer': subscription.party,
    'payment_gateway': subscription.payment_gateway,
    'payment_configuration': subscription.payment_method_configuration
  }
  payment_url = frappe.utils.get_url() + f"/stripe_plus_subs_checkout?{urlencode(params)}"
  recipient = get_representative_email_address(
    representative=subscription.user_account_representative,
    as_dict=False,
    log_title=f"Failed to send payment URL for {subscription.name}",
  )

  subscription_plan_list, subscription_plan_grand_total = calculate_subscription_plan_total(subscription)

  subscription_plan_table = frappe.render_template(
    "erpusa/templates/html/subscription_plan_table.html", {
      "subscription_plan_list": subscription_plan_list,
      "subscription_plan_grand_total": subscription_plan_grand_total
    }
  )
  subject = frappe.db.get_single_value("Stripe Plus Settings", "subscription_email_subject") or _("Request to Subscribe and Initiate Payment via Stripe")
  subject_template = Template(subject)

  if is_text_editor_set(frappe.db.get_single_value("Stripe Plus Settings", "subscription_email_message")):
    message_template = Template(frappe.db.get_single_value("Stripe Plus Settings", "subscription_email_message"))
    message = message_template.render(
      customer=subscription.party,
      company=subscription.company,
      name=f"<b>{subscription.friendly_name or subscription.name}</b>",
      start_date=subscription.start_date,
      end_date=subscription.end_date,
      payment_url=f'<span> <a href="{payment_url}" target="_blank">here</a> </span>',
      subscription_plan_table=subscription_plan_table
    )

  else:
    message = _(
      """
      Dear {},
      <p>This email confirms your recent subscription to <b>{}</b> with {}.  We're excited to have you as a subscriber!</p>
      <p>Here's what you're subscribe to:</p>
      <p>{}</p>
      <p>To set up your payment methods and automatic payments, click <span> <a href="{}" target="_blank">here</a> </span>.</p>.
      """
    ).format(subscription.party, subscription.friendly_name or subscription.name, subscription.company, subscription_plan_table, payment_url)

  try:
    frappe.sendmail(
      subject=subject_template.render(name=subscription.name, start_date=subscription.start_date, end_date=subscription.end_date),
      message=message,
      recipients=[recipient],
      reference_doctype="Subscription",
      reference_name=subscription.name
    )

  except Exception as e:
    frappe.log_error("Error Sending Subscription Payment", str(e))

  frappe.db.set_value("Subscription", subscription.name, "payment_url", payment_url)
  frappe.db.set_value("Subscription", subscription.name, "email_queue", frappe.db.exists("Email Queue", {"reference_doctype": "Subscription", "reference_name": subscription.name}))
  frappe.msgprint(_("An email was queued. Refresh the page from time to time to see updates."))

@frappe.whitelist()
def cancel_subscription(subscription_name):
  subscription_doc = frappe.get_doc("Subscription", subscription_name)
  
  try:
    subscription_doc.cancel_subscription()
  except Exception as e:
    frappe.throw(_("Failed to cancel subscription"), str(e))
  
  if subscription_doc.stripe_subscription_id:
    stripe.api_key = get_api_key_secret(payment_gateway=subscription_doc.payment_gateway)
    
    try:
      subscription = stripe.Subscription.retrieve(subscription_doc.stripe_subscription_id)
    except Exception as e:
      frappe.throw(_("Failed to find the associated Stripe.com subscription: {}").format(subscription_doc.stripe_subscription_id), str(e))

    if subscription.status in ["canceled", "incomplete_expired", "incomplete"]:
      frappe.db.set_value("Subscription", subscription_name, "stripe_subscription_status", SUBSCRIPTION_STATUS_VERBOSE[subscription.status])
    
    else:
      try:
        subscription = stripe.Subscription.cancel(subscription_doc.stripe_subscription_id)
      except Exception as e:
        frappe.throw(_("Failed to cancel associated Stripe.com subscription: {}").format(subscription_doc.stripe_subscription_id), str(e))
        
      frappe.db.set_value("Subscription", subscription_name, "stripe_subscription_status", subscription.status.title())

def validate_subscription_plan_stripe_price(subscription_plan, method=None):
  if subscription_plan.stripe_price_id and (subscription_plan.has_value_changed("currency") or \
    subscription_plan.has_value_changed("item") or \
    subscription_plan.has_value_changed("price_determination") or \
    subscription_plan.has_value_changed("price_list")or \
    subscription_plan.has_value_changed("cost") or \
    subscription_plan.has_value_changed("billing_interval") or \
  subscription_plan.has_value_changed("billing_interval_count") ):
    frappe.throw(_("This field can't be modified as the Subscription Plan has been registered to stripe.com"))

def update_stripe_product(item, method=None):
  if item.stripe_product_id and (item.has_value_changed("item_name") or item.has_value_changed("description")):
    subscription_plan_detail = frappe.qb.DocType("Subscription Plan Detail")
    subscription_plan = frappe.qb.DocType("Subscription Plan")

    query = (
        frappe.qb.from_(subscription_plan_detail)
        .select(subscription_plan_detail.parent)
        .inner_join(subscription_plan)
        .on(subscription_plan_detail.plan == subscription_plan.name)
        .where(subscription_plan.item == item.name)
    )

    subscriptions = query.run()
    
    if subscriptions:
      stripe.api_key = get_api_key_secret(payment_gateway=frappe.db.get_value("Subscription", subscriptions[0][0], "payment_gateway"))
      
      try:
        product = stripe.Product.modify(
          item.stripe_product_id,
          name=item.item_name,
          description=item.description
        )
      except Exception as e:
        frappe.log_error(_("Failed to update Stripe product: {}").format(item.stripe_product_id), str(e))
    

def is_text_editor_set(html_content):
  if not html_content:
    return False

  text = re.sub('<[^<]+?>', '', html_content or '')
  return text.strip()

def unbind_email_queue_from_subscription(subscription, method=None):
  if subscription.email_queue:
    frappe.db.set_value("Email Queue", subscription.email_queue, "reference_name", None)

  

