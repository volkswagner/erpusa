# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
import stripe
import json
from frappe.utils import now_datetime
from datetime import timedelta
from payments.templates.pages.stripe_checkout import get_api_key
from payments.payment_gateways.doctype.stripe_settings.stripe_settings import (get_gateway_controller)
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret, get_pm_configuration_methods

no_cache = 1

def get_context(context):
    if frappe.form_dict:
        context.subscription = frappe.form_dict["subscription_name"]
        subscription_data = frappe.db.get_value("Subscription", context.subscription, ["payment_gateway", "party", "payment_configuration"], as_dict=True)
        context.gateway_controller = get_gateway_controller(
            "Subscription", context.subscription, subscription_data["payment_gateway"]
        )
        
        subscription_updates_count = frappe.db.count(
            "Subscription Update",
            filters={
                "parent": context.subscription,
                "update_type": "Payment Method Change",
                "creation": [
                    "between", [
                        now_datetime() - timedelta(minutes=frappe.db.get_single_value("Stripe Plus Settings", "timeframe")),
                        now_datetime()
                    ]
                ]
            }
        )
        
        if subscription_updates_count >= frappe.db.get_single_value("Stripe Plus Settings", "no_of_times"):
            frappe.redirect_to_message(
                _("Changing payment method not allowed"),
                _("You have reached the allowable times to change your payment method. You can only change it {} times every {} minutes.")
                .format(frappe.db.get_single_value("Stripe Plus Settings", "no_of_times"), frappe.db.get_single_value("Stripe Plus Settings", "timeframe")),
            )
            frappe.local.flags.redirect_location = frappe.local.response.location
            raise frappe.Redirect
        
        context.publishable_key = get_api_key("Subscription", context.gateway_controller)
        context.customer = subscription_data["party"]
        context.payment_configuration = subscription_data["payment_configuration"]
        context.subscription_display_name = frappe.db.get_value("Subscription", context.subscription, "friendly_name") or context.subscription
        context.methods = get_pm_configuration_methods(frappe.db.get_value("Subscription", context.subscription, "payment_method_configuration"), False)
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


@frappe.whitelist(allow_guest=True)
def create_change_payment_session():
    data = json.loads(frappe.request.data)
    stripe.api_key = get_api_key_secret(data.get("gateway_controller"))
    payment_method_configuration = frappe.db.get_value("Subscription", data.get("subscription"), "payment_method_configuration")
    
    try:
        session = stripe.checkout.Session.create(
            ui_mode = "embedded",
            mode="setup",
            currency='USD', #change this
            customer=frappe.db.get_value("Customer", data.get("customer"), "stripe_customer_id"),
            setup_intent_data={
                "metadata": {
                    "erp_subscription_name": data.get("subscription"),
                    "stripe_subscription_id": frappe.db.get_value("Subscription", data.get("subscription"), "stripe_subscription_id")
                }
            },
            return_url=f"{frappe.utils.get_url()}/stripe_plus_subs_change_payment_return?session_id={{CHECKOUT_SESSION_ID}}&subscription_name={data.get('subscription')}",
            payment_method_configuration=frappe.db.get_value("Stripe Payment Method Configuration", payment_method_configuration, "stripe_configuration_id")
        )
        
    except Exception as e:
        return str(e)
    
    return {"clientSecret": session['client_secret']}
