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

no_cache = 1

def get_context(context):
    if frappe.form_dict:
        context.subscription = frappe.form_dict["subscription_name"]
        payment_gateway = frappe.db.get_value("Subscription", context.subscription, "payment_gateway")
        context.gateway_controller = get_gateway_controller(
            "Subscription", context.subscription, payment_gateway
        )
        context.publishable_key = get_api_key("Subscription", context.gateway_controller)
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
        
        if frappe.db.get_value("Subscription", context.subscription, "status") == "Cancelled":
            frappe.redirect_to_message(
                _("Subscription is no longer active.").format(context.subscription),
                _("Subscription <b>{}</b> was cancelled. If you believe this is a mistake, please contact {}.").format(context.subscription, context.company),
            )
            frappe.local.flags.redirect_location = frappe.local.response.location
            raise frappe.Redirect
        
        if frappe.db.get_value("Subscription", context.subscription, "stripe_subscription_id"):
            status = frappe.db.get_value("Subscription", context.subscription, "stripe_subscription_status") or frappe.db.get_value("Subscription", context.subscription, "status")
            frappe.redirect_to_message(
                _("Payment has already been initiated.").format(context.subscription),
                _("Subscription <b>{}</b> is already {}. Thank you for your business!").format(context.subscription, status.lower()),
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
def create_checkout_session(subscription_name, api_key):
    subscription_doc = frappe.get_doc("Subscription", subscription_name)
    stripe.api_key = api_key
    line_items = []
    
    for subscription_plan in subscription_doc.plans:
        line_items.append({
            'price': frappe.db.get_value("Subscription Plan", subscription_plan.plan, "stripe_price_id"),
            'quantity': subscription_plan.qty
        })

    subscription_data = {
        "metadata": {
            "erp_subscription_name": subscription_doc.name,
            "proration_behavior": "none"
        },
    }

    # if str(subscription_doc.start_date) != str(frappe.utils.today()):
    #     subscription_data['billing_cycle_anchor'] = int(
    #         formulate_timestamp(subscription_doc.start_date)
    #     )

    if subscription_doc.trial_period_end:
        subscription_data['trial_end'] = int(
            formulate_timestamp(
                subscription_doc.current_invoice_start
            )
        )


    else:
        billing_cycle_anchor = subscription_doc.start_date
        if str(subscription_doc.start_date) < str(frappe.utils.today()):
            billing_cycle_anchor = subscription_doc.current_invoice_start

        if str(subscription_doc.current_invoice_start) < str(frappe.utils.today()):
            billing_cycle_anchor = add_to_date(subscription_doc.current_invoice_end, days=1) 

        subscription_data['billing_cycle_anchor'] = int(
            formulate_timestamp(billing_cycle_anchor)
        )

    try:
        session = stripe.checkout.Session.create(
            ui_mode="embedded",
            mode="subscription",
            customer=frappe.db.get_value("Customer", subscription_doc.party, "stripe_customer_id"),
            line_items=line_items,
            subscription_data=subscription_data,
            return_url=f"{frappe.utils.get_url()}/stripe_plus_subs_return?session_id={{CHECKOUT_SESSION_ID}}&subscription_name={subscription_doc.name}&payment_gateway={subscription_doc.payment_gateway}",
            payment_method_configuration=frappe.db.get_value("Stripe Payment Method Configuration", subscription_doc.payment_method_configuration, "stripe_configuration_id")
        )
        
    except Exception as e:
        return str(e)
    
    frappe.db.set_value("Subscription", subscription_doc.name, "stripe_session_id", session.id)
    
    return {"clientSecret": session['client_secret']}

@frappe.whitelist(allow_guest=True)
def create_fetch_checkout_session():
    data = json.loads(frappe.request.data)
    subscription_name = data.get("subscription")
    stripe.api_key = get_api_key_secret(
        payment_gateway=frappe.db.get_value("Subscription", subscription_name, "payment_gateway")
    )

    # check if intent has already been made
    stripe_session_id = frappe.db.get_value("Subscription", subscription_name, "stripe_session_id")

    if stripe_session_id:
        try:
            checkout = stripe.checkout.Session.retrieve(stripe_session_id)

            if checkout['status'] != "complete":
                return create_checkout_session(subscription_name, stripe.api_key)
                
            else:
                return {
                    "clientSecret": checkout['client_secret'],
                    "redirect": ""
                }
            
        except Exception as e:
            return {"error": str(e)}, 403
        
    else:
        
        return create_checkout_session(subscription_name, stripe.api_key)

@frappe.whitelist(allow_guest=True)
def get_session_info(session_id, gateway_controller):
    stripe.api_key = get_api_key_secret(gateway_controller)
    
    session = stripe.checkout.Session.retrieve(session_id)

    return {
        'status': session.status,
        'amount': session.amount_total
    }
