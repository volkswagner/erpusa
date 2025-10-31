import frappe
from frappe import _
from frappe.utils import today, getdate
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_representative_email_address, get_representative_phone

def check_card_expiration():
    card_expiry_notification_lead_time = frappe.db.get_single_value("Stripe Plus Settings", "card_expiry_notification_lead_time")
    card_expiry_notification_repeat = frappe.db.get_single_value("Stripe Plus Settings", "card_expiry_notification_repeat")
    subscriptions = frappe.db.get_all(
        "Subscription",
        filters={
            "status": "Active",
            "stripe_subscription_status": ["in", ["Active", "Trialing", "Paused", "Past Due", "Unpaid"]],
            "card_expiration": ["not in", ["", None]]
        },
        fields=["party", "name", "card_expiration", "card_expiry_notification_count", "user_account_representative", "friendly_name"]
    )

    cards_about_to_expire = []

    for sub in subscriptions:
        ce_year, ce_month = sub['card_expiration'].split("-")
        month_difference = int(ce_month) - getdate(today()).month
        card_expiry_notification_count = sub['card_expiry_notification_count'] or 0

        if getdate(today()).year == int(ce_year) and (month_difference <= card_expiry_notification_lead_time):
            if card_expiry_notification_count == 1 and card_expiry_notification_repeat == "Notify Once":
                continue
            if card_expiry_notification_repeat == "Notify Only at the Earliest and Closest Month" and (month_difference != card_expiry_notification_lead_time and month_difference != 0):
                continue

            cards_about_to_expire.append({
                **sub, 
                'email': get_representative_email_address(sub['user_account_representative'])['email_id'],
                'phone': get_representative_phone(sub['user_account_representative'])['phone'],
                'month_difference': month_difference,
                'url': frappe.utils.get_url_to_form("Subscription", sub['name'])
            })
            frappe.db.set_value("Subscription", sub['name'], "card_expiry_notification_count", card_expiry_notification_count + 1)
    

    notify_card_expiration(cards_about_to_expire)

def notify_card_expiration(cards_about_to_expire):
    if cards_about_to_expire:
        message = frappe.render_template(
            "erpusa/templates/html/card_expiry_notification.html", {
                "data": cards_about_to_expire,
            }
        )
        recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")

        frappe.sendmail(
            recipients=recipients.split(),
            subject=_("Action Required: Expiring Payment Card Linked to Subscriptions"),
            message=message,
            now=True
        )
    