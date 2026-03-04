# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
import stripe
import json
import datetime
from payments.templates.pages.stripe_checkout import get_api_key
from payments.payment_gateways.doctype.stripe_settings.stripe_settings import (get_gateway_controller)
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_api_key_secret
from frappe.utils import add_to_date
from urllib.parse import urlencode

no_cache = 1

def get_context(context):
    if frappe.form_dict:
        context.subscription = frappe.form_dict["subscription_name"]
        payment_gateway = frappe.db.get_value("Subscription", context.subscription, "payment_gateway")
        context.gateway_controller = get_gateway_controller(
            "Subscription", context.subscription, payment_gateway
        )
        context.publishable_key = get_api_key("Subscription", context.gateway_controller)
        context.subscription = frappe.form_dict["subscription_name"]
        subscription_details = frappe.db.get_value("Subscription", context.subscription, ["friendly_name", "status", "stripe_subscription_id", "stripe_subscription_status"], as_dict=True)
        context.subscription_display_name = subscription_details["friendly_name"] or context.subscription
        context.customer = frappe.db.get_value("Subscription", context.subscription, "party")
        context.payment_configuration = frappe.db.get_value("Subscription", context.subscription, "payment_method_configuration")
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
        
        if subscription_details["status"] == "Cancelled":
            frappe.redirect_to_message(
                _("Subscription is no longer active.").format(context.subscription),
                _("Subscription <b>{}</b> was cancelled. If you believe this is a mistake, please contact {}.").format(context.subscription_display_name, context.company),
            )
            frappe.local.flags.redirect_location = frappe.local.response.location
            raise frappe.Redirect
        
        if subscription_details["stripe_subscription_id"]:
            frappe.redirect_to_message(
                _("Payment has already been initiated.").format(context.subscription_display_name),
                _("Subscription <b>{}</b> is already {}. Thank you for your business!").format(context.subscription, subscription_details["stripe_subscription_status"].lower()),
            )
            frappe.local.flags.redirect_location = frappe.local.response.location
            raise frappe.Redirect

def formulate_timestamp(date):
    if isinstance(date, str):
        date = datetime.datetime.strptime(date, "%Y-%m-%d").date()

    # Combine with midnight
    dt = datetime.datetime.combine(date, datetime.time.min)

    # Make it UTC-aware
    import pytz
    dt_utc = pytz.UTC.localize(dt)

    # Get timestamp
    timestamp = dt_utc.timestamp()

    return timestamp


@frappe.whitelist(allow_guest=True)
def create_fetch_checkout_session():
    data = json.loads(frappe.request.data)
    subscription_name = data.get("subscription")
    stripe.api_key = get_api_key_secret(
        payment_gateway=frappe.db.get_value("Subscription", subscription_name, "payment_gateway")
    )

    subscription_doc = frappe.get_doc("Subscription", subscription_name)
    line_items = []
    return_url_params = {
        'session_id': "{CHECKOUT_SESSION_ID}",
        'subscription_name': data.get('subscription'),
        'payment_gateway': frappe.db.get_value('Subscription', data.get('subscription'), 'payment_gateway')
    }
    
    for subscription_plan in frappe.db.get_all("Subscription Plan Detail", filters={"parent": data.get("subscription")}, fields=["plan", "qty"]):
        line_items.append({
            'price': frappe.db.get_value("Subscription Plan", subscription_plan.plan, "stripe_price_id"),
            'quantity': subscription_plan.qty
        })
    try:
        session = stripe.checkout.Session.create(
            ui_mode = "embedded",
            mode="subscription",
            customer=frappe.db.get_value("Customer", data.get("customer"), "stripe_customer_id"),
            line_items=line_items,
            subscription_data={
                "metadata": {
                    "erp_subscription_name": data.get("subscription")
                }
            },
            return_url=f"{frappe.utils.get_url()}/stripe_plus_subs_return?{return_url_params}",
            payment_method_configuration=frappe.db.get_value("Stripe Payment Method Configuration", subscription_doc.payment_method_configuration, "stripe_configuration_id")
        )
        
    except Exception as e:
        return str(e)
    
    return {"clientSecret": session['client_secret']}

@frappe.whitelist(allow_guest=True)
def get_session_info(session_id, gateway_controller):
    stripe.api_key = get_api_key_secret(gateway_controller)
    
    session = stripe.checkout.Session.retrieve(session_id)

    return {
        'status': session.status,
        'amount': session.amount_total
    }
