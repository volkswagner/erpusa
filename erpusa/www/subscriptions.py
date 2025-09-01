import frappe
from frappe import _
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import calculate_subscription_plan_total

def get_context(context):
    if frappe.session.user == "Guest":
        frappe.throw(_("You must be logged in to access this page."), frappe.PermissionError)
    
    context.no_cache = 1
    context.show_sidebar = True
    context.title = "My Subscriptions"
    context.customer = frappe.db.exists("Customer", {"user": frappe.session.user})
    context.subscriptions = []
    if context.customer:
        for subscription in frappe.db.get_all("Subscription", filters={"party": context.customer}, pluck="name", order_by="status ASC"):
            subscription_data = frappe.get_doc("Subscription", subscription).as_dict()
            subscription_data["subscription_plan_list"], subscription_data["total"] = calculate_subscription_plan_total(subscription_data)
            
            context.subscriptions.append(subscription_data)
        