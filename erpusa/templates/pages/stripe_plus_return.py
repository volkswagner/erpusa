import frappe
import stripe
from frappe import _
from payments.templates.pages.stripe_checkout import get_api_key
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret
from frappe.utils import fmt_money

no_cache = 1

def get_context(context):
    # all these keys exist in form_dict
    if "session_id" in frappe.form_dict and ("reference_docname" in frappe.form_dict or "gateway_controller" in frappe.form_dict):
        context.publishable_key = get_api_key(frappe.form_dict.reference_docname, frappe.form_dict.gateway_controller)
        stripe.api_key = get_api_key_secret(gateway_controller=frappe.form_dict.gateway_controller)
        context.to_pay_doctype = frappe.form_dict.to_pay_doctype
        context.to_pay_id = frappe.form_dict.to_pay_id
        context.amount = fmt_money(int(frappe.form_dict.amount)/100)
        context.payment_intent_status = None

        try:
            checkout_session = stripe.checkout.Session.retrieve(frappe.form_dict['session_id'])

            if checkout_session:
                try:
                    payment_intent = stripe.PaymentIntent.retrieve(checkout_session['payment_intent'])

                    if payment_intent:
                        context.payment_intent_status = payment_intent['status']

                except Exception as e:
                    frappe.redirect_to_message(
                        _("An error occured while connecting to Stripe"),
                        _(str(e)),
                    )
                    frappe.local.flags.redirect_location = frappe.local.response.location
                    raise frappe.Redirect


        except Exception as e:
            frappe.redirect_to_message(
                _("An error occured while connecting to Stripe"),
                _(str(e)),
            )
            frappe.local.flags.redirect_location = frappe.local.response.location
            raise frappe.Redirect

    else:
        frappe.redirect_to_message(
            _("Some information is missing"),
            _("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise frappe.Redirect