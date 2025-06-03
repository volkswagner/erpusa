import frappe
import json
import frappe.utils
from frappe import _
from frappe.utils import now
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

def get_customer_field_value(name, field):
    return frappe.db.get_value("Sales Invoice", name, field)

@frappe.whitelist()
def create_bulk_payment_entry(invoices, paid_amount=None, reference_no=None, reference_date=None):
    if not paid_amount and not reference_no and not reference_date:
        frappe.throw(_("Fields Paid Amount, Reference No and Reference Date are required."))

    if float(paid_amount) <= 0.00:
        frappe.throw(_("Paid Amount can't be negative or zero."))

    invoices = json.loads(invoices)
    customer = get_customer_field_value(invoices[0]["name"], "customer")
    company = get_customer_field_value(invoices[0]["name"], "company")

    for invoice in invoices:
        if get_customer_field_value(invoice["name"], "docstatus") != 1:
            frappe.throw(_("Can only create invoices for submitted invoices."))
        if get_customer_field_value(invoice["name"], "customer") != customer:
            frappe.throw(_("Can only create invoices if the customers are the same."))
        

    pe_doc = get_payment_entry("Sales Invoice", invoices[0]["name"])
    pe_doc.paid_amount = float(paid_amount)
    pe_doc.reference_no = reference_no
    pe_doc.reference_date = reference_date
    pe_doc.references = []

    for invoice in invoices:
        pe_doc.append("references", {
            "account": frappe.db.get_value("Company", company, "default_receivable_account"),
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice["name"],
            "total_amount": float(invoice["grand_total"]),
            "outstanding_amount": float(invoice["grand_total"]),
            "allocated_amount": float(invoice["grand_total"]),
        })

    pe_doc.save()

    return pe_doc.name