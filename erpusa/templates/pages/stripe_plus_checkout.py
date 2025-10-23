# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.utils import fmt_money
import stripe
import json
from decimal import Decimal, ROUND_DOWN
from payments.templates.pages.stripe_checkout import is_a_subscription, get_api_key
from payments.payment_gateways.doctype.stripe_settings.stripe_settings import (get_gateway_controller)
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import (
    get_api_key_secret,
    get_customer_funding_instructions,
)

expected_keys = ["reference_doctype", "reference_docname", "payment_gateway", "description", "access_token"]

def get_context(context):
    context.no_cache = 1

    # all these keys exist in form_dict
    if frappe.form_dict:
        url_parameter = frappe.form_dict
        if "payment_gateway" not in url_parameter:
            url_parameter["payment_gateway"] = ""

        ek_set = set(expected_keys)
        fd_set = set(list(url_parameter))
        
        if ek_set.issubset(fd_set):
            for key in expected_keys:
                context[key] = url_parameter[key]

            paymentRequestAccessToken = frappe.db.get_value(context.reference_doctype, context.reference_docname, "stripe_plus_access_token")
            if (context.access_token != paymentRequestAccessToken):
                redirect_for_missing_info()

            context.to_pay_doctype = frappe.db.get_value(context.reference_doctype, context.reference_docname, "reference_doctype")
            context.to_pay_docname = frappe.db.get_value(context.reference_doctype, context.reference_docname, "reference_docname")

            paymentRequestStatus = frappe.db.get_value(context.reference_doctype, context.reference_docname, "status")

            if paymentRequestStatus == "Paid":
                frappe.redirect_to_message(
                    _("This payment request has been fulfilled."),
                    _("The {doctype} is already paid! Thank you for your business.").format(doctype=context.to_pay_doctype),
                )
                frappe.local.flags.redirect_location = frappe.local.response.location
                raise frappe.Redirect
            elif paymentRequestStatus == "Cancelled":
                frappe.redirect_to_message(
                    _("This payment request is no longer valid."),
                    _("The payment request was cancelled and this link is no longer valid. You may have received an updated payment request for {doctype} {docname} instead.").format(doctype=context.to_pay_doctype, docname=context.to_pay_docname),
                )
                frappe.local.flags.redirect_location = frappe.local.response.location
                raise frappe.Redirect
            else:
                context.gateway_controller = get_gateway_controller(
                    context.reference_doctype, context.reference_docname, frappe.form_dict["payment_gateway"]
                )
                context.publishable_key = get_api_key(context.reference_docname, context.gateway_controller)
                
                settings_company = frappe.db.get_single_value("Stripe Plus Settings", "payment_page_company_name")
                settings_header_image = frappe.db.get_single_value("Stripe Plus Settings", "payment_page_company_logo")

                if settings_company:
                    context.company = settings_company

                else: 
                    context.company = frappe.db.get_value(context.reference_doctype, context.reference_docname, "company")

                if settings_company and settings_header_image:
                    context.header_image = settings_header_image

                else:
                    context.header_image = frappe.db.get_value("Company", context.company, "company_logo")
                
                context.title = context.company
                context.to_pay_id = frappe.db.get_value(context.reference_doctype, context.reference_docname, "reference_name")
                context.order_id = context.reference_docname

                context.payer_email = frappe.db.get_value(context.reference_doctype, context.reference_docname, "email_to")
                context.payer_name = frappe.db.get_value(context.reference_doctype, context.reference_docname, "party_name")

                if frappe.db.get_value(context.reference_doctype, context.reference_docname, "payment_method_configuration"):
                    pm_configuration_doc = frappe.db.get_value(context.reference_doctype, context.reference_docname, "payment_method_configuration")
                    context.pm_configuration = frappe.db.get_value("Stripe Payment Method Configuration", pm_configuration_doc, "stripe_configuration_id")
                
                else:
                    context.pm_configuration = None

                paymentRequestAmount = frappe.db.get_value(context.reference_doctype, context.reference_docname, "outstanding_amount")
                paymentRequestCurrencyDocname = frappe.db.get_value(context.reference_doctype, context.reference_docname, "currency")
                paymentRequestCurrencyName = frappe.db.get_value("Currency", paymentRequestCurrencyDocname, "currency_name")
                context.currency = paymentRequestCurrencyName
                context.amount_float = paymentRequestAmount
                context["amount"] = fmt_money(amount=paymentRequestAmount, currency=paymentRequestCurrencyName)

                if is_a_subscription(context.reference_doctype, context.reference_docname):
                    payment_plan = frappe.db.get_value(
                        context.reference_doctype, context.reference_docname, "payment_plan"
                    )
                    recurrence = frappe.db.get_value("Payment Plan", payment_plan, "recurrence")

                    context["amount"] = context["amount"] + " " + _(recurrence)
        else:
            redirect_for_missing_info()
    else:
        redirect_for_missing_info()

def redirect_for_missing_info():
    frappe.redirect_to_message(
            _("Some information is missing"),
            _("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
        )
    frappe.local.flags.redirect_location = frappe.local.response.location
    raise frappe.Redirect 

def create_payment_intent(data, customer_id):
    amount_in_decimal = (Decimal(data.get('amount')) * 100).quantize(Decimal("1"), rounding=ROUND_DOWN)
    amount_in_int = int(amount_in_decimal)
    
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_in_int,
            currency='usd',
            customer=customer_id,
            setup_future_usage="on_session",
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

@frappe.whitelist(allow_guest=True)
def create_fetch_payment_intent():
    data = json.loads(frappe.request.data)
    stripe.api_key = get_api_key_secret(data.get('gateway_controller'))

    # check if intent has already been made
    stripe_intent_id = frappe.db.get_value("Payment Request", data.get('request_name'), "stripe_intent_id")
    payment_request_customer = frappe.db.get_value("Payment Request", data.get('request_name'), "party")
    stripe_customer_id = frappe.db.get_value("Customer", payment_request_customer, "stripe_customer_id")

    # load payment amount from payment request
    data["amount"] = frappe.db.get_value("Payment Request", data.get('request_name'), "outstanding_amount")

    if stripe_intent_id:
        try:
            payment_intent = stripe.PaymentIntent.retrieve(stripe_intent_id)
            # redirect to message page if success/processing

            if payment_intent["status"] in ["succeeded", "processing"]:
                return {
                    "client_secret": "",
                    "redirect": f"/message?title=This+payment+request+has+been+fulfilled.&message=The+{data.get('doctype')}+is+already+paid!+Thank+you+for+your+business.&type=success"
                }
            # return client secret if incomplete

            elif payment_intent["status"] in ["requires_action", "requires_capture", "requires_confirmation", "requires_payment_method"]:
                return {
                    "clientSecret": payment_intent['client_secret'],
                    "redirect": ""
                }
            # create new intent if cancelled
    
            else:
                return create_payment_intent(data, stripe_customer_id)
        
        except Exception as e:
            return {"error": str(e)}, 403
        
    else:
        # create new intent if no intent id
        return create_payment_intent(data, stripe_customer_id)
    
@frappe.whitelist(allow_guest=True)
def create_customer_session():
    data = json.loads(frappe.request.data)
    stripe.api_key = get_api_key_secret(data.get('gateway_controller'))

    payment_request_customer = frappe.db.get_value("Payment Request", data.get('request_name'), "party")
    stripe_customer_id = frappe.db.get_value("Customer", payment_request_customer, "stripe_customer_id")

    customerSession = stripe.CustomerSession.create(
        customer=stripe_customer_id,
        components={
            "payment_element": {
                "enabled": True,
                "features": {
                    "payment_method_redisplay": "enabled",
                    "payment_method_save": "enabled",
                    "payment_method_save_usage": "on_session",
                    "payment_method_remove": "enabled",
                },
            },
        },
    )

    return {
        "customerSessionClientSecret": customerSession.client_secret,
    }