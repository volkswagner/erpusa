# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.utils import fmt_money
import stripe
import json
import datetime
from decimal import Decimal, ROUND_DOWN
from payments.templates.pages.stripe_checkout import expected_keys, is_a_subscription, get_api_key
from payments.payment_gateways.doctype.stripe_settings.stripe_settings import (get_gateway_controller)
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret, get_customer_contact, get_representative_email_address

def get_context(context):
    if frappe.form_dict:
        context.gateway_controller = get_gateway_controller(
            "Subscription", frappe.form_dict["subscription_name"], frappe.form_dict["payment_gateway"]
        )
        context.publishable_key = get_api_key("Subscription", context.gateway_controller)
        context.subscription = frappe.form_dict["subscription_name"]
        context.customer = frappe.form_dict["customer"]
        context.payment_configuration = frappe.form_dict["payment_configuration"]
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
        
        if frappe.db.get_value("Subscription", context.subscription, "stripe_subscription_id"):
            frappe.redirect_to_message(
                _("Payment has already been initiated.").format(context.subscription),
                _("Subscription <b>{}</b> is already {}. Thank you for your business!").format(context.subscription, frappe.db.get_value("Subscription", context.subscription, "stripe_subscription_status").lower()),
            )
            frappe.local.flags.redirect_location = frappe.local.response.location
            raise frappe.Redirect


@frappe.whitelist(allow_guest=True)
def create_checkout_session(data):
    stripe.api_key = get_api_key_secret(data.get("gateway_controller"))
    line_items = []
    
    for subscription_plan in frappe.db.get_all("Subscription Plan Detail", filters={"parent": data.get("subscription")}, fields=["plan", "qty"]):
        line_items.append({
            'price': frappe.db.get_value("Subscription Plan", subscription_plan.plan, "stripe_price_id"),
            'quantity': subscription_plan.qty
        })
    
    try:
        session = stripe.checkout.Session.create(
            ui_mode = 'embedded',
            mode='subscription',
            customer=frappe.db.get_value("Customer", data.get("customer"), "stripe_customer_id"),
            line_items=line_items,
            subscription_data={
                "metadata": {
                    "erp_subscription_name": data.get("subscription")
                }
            },
            return_url=f"{frappe.utils.get_url()}/stripe_plus_subs_return",
            payment_method_configuration=frappe.db.get_value("Stripe Payment Method Configuration", data.get("payment_configuration"), "stripe_configuration_id")
        )
        
    except Exception as e:
        return str(e)
    
    return {"clientSecret": session['client_secret']}

@frappe.whitelist(allow_guest=True)
def create_fetch_checkout_session():
    data = json.loads(frappe.request.data)
    stripe.api_key = get_api_key_secret(data.get('gateway_controller'))

    # check if intent has already been made
    stripe_checkout_id = frappe.db.get_value("Subscription", data.get('request_name'), "stripe_intent_id")

    if stripe_checkout_id:
        try:
            checkout = stripe.checkout.Session.retrieve(stripe_checkout_id)

            if checkout['status'] != "complete":
                return create_checkout_session(data)
                
            else:
                return {
                    "clientSecret": checkout['client_secret'],
                    "redirect": ""
                }
            
        except Exception as e:
            return {"error": str(e)}, 403
        
    else:
        
        return create_checkout_session(data)

@frappe.whitelist(allow_guest=True)
def get_session_status(session_id, gateway_controller):
    stripe.api_key = get_api_key_secret(gateway_controller)
    
    session = stripe.checkout.Session.retrieve(session_id)

    return session.status
    
    
    #?subscription={data.get('subscription')}&gateway_controller={data.get('gateway_controller')}
