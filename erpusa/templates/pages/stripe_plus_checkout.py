# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.utils import fmt_money
import stripe
import json
from payments.templates.pages.stripe_checkout import expected_keys, is_a_subscription, get_api_key
from payments.payment_gateways.doctype.stripe_settings.stripe_settings import (get_gateway_controller)
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import (get_api_key_secret)

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
            context.to_pay_doctype = frappe.db.get_value(context.reference_doctype, context.reference_docname, "reference_doctype")
            if frappe.db.get_value(context.reference_doctype, context.reference_docname, "status") == "Paid":
                frappe.redirect_to_message(
                    _("This payment request has been fulfilled."),
                    _("The {doctype} is already paid! Thank you for your business.").format(doctype=context.to_pay_doctype),
                )
                frappe.local.flags.redirect_location = frappe.local.response.location
                raise frappe.Redirect
            else:
                context.gateway_controller = get_gateway_controller(
                    context.reference_doctype, context.reference_docname, frappe.form_dict["payment_gateway"]
                )
                context.publishable_key = get_api_key(context.reference_docname, context.gateway_controller)
                context.company = frappe.db.get_value(context.reference_doctype, context.reference_docname, "company")
                context.header_image = frappe.db.get_value("Company", context.company, "company_logo")
                
                context.to_pay_id = frappe.db.get_value(context.reference_doctype, context.reference_docname, "reference_name")
                if not frappe.db.get_value(context.reference_doctype, context.reference_docname, "use_default_methods"):
                    pm_configuration_doc = frappe.db.get_value(context.reference_doctype, context.reference_docname, "payment_methods")
                    context.pm_configuration = frappe.db.get_value("Stripe Payment Method Configuration", pm_configuration_doc, "stripe_configuration_id")
                else:
                    context.pm_configuration = None
                context.amount_int = context["amount"]
                context["amount"] = fmt_money(amount=context["amount"], currency=context["currency"])

                if is_a_subscription(context.reference_doctype, context.reference_docname):
                    payment_plan = frappe.db.get_value(
                        context.reference_doctype, context.reference_docname, "payment_plan"
                    )
                    recurrence = frappe.db.get_value("Payment Plan", payment_plan, "recurrence")

                    context["amount"] = context["amount"] + " " + _(recurrence)

    else:
        frappe.redirect_to_message(
            _("Some information is missing"),
            _("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect

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

@frappe.whitelist(allow_guest=True)
def create_fetch_payment_intent():
    data = json.loads(frappe.request.data)
    stripe.api_key = get_api_key_secret(data.get('gateway_controller'))

    # check if intent has already been made
    stripe_intent_id = frappe.db.get_value("Payment Request", data.get('request_name'), "stripe_intent_id")
    if stripe_intent_id:
        try:
            intent = stripe.PaymentIntent.retrieve(stripe_intent_id)
            # redirect to message page if success/processing
            if intent["status"] in ["succeeded", "processing"]:
                return {
                    "client_secret": "",
                    "redirect": f"/message?title=This+payment+request+has+been+fulfilled.&message=The+{data.get('doctype')}+is+already+paid!+Thank+you+for+your+business.&type=success"
                }
            # return client secret if incomplete
            elif intent["status"] in ["requires_action", "requires_capture", "requires_confirmation", "requires_payment_method"]:
                return {
                    "clientSecret": intent['client_secret'],
                    "redirect": ""
                }
            # create new intent if cancelled
            else:
                return create_payment_intent(data)
        except Exception as e:
            return {"error": str(e)}, 403
    else:
        # create new intent if no intent id
        return create_payment_intent(data)