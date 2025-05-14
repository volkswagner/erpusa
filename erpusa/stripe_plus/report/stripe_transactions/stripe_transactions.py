# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

# erpusa/stripe_plus/report/stripe_transactions_report/stripe_transactions_report.py

import frappe

def execute(filters=None):
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    columns = [
        {"label": "Created", "fieldname": "created", "fieldtype": "Datetime", "width": 160},
        {"label": "Charge ID", "fieldname": "charge_id", "fieldtype": "Data", "width": 180},
        {"label": "Available On", "fieldname": "available_on", "fieldtype": "Date", "width": 120},
        {"label": "Payment Entry", "fieldname": "payment_entry", "fieldtype": "Link", "options": "Payment Entry", "width": 140},
        {"label": "Payment Request", "fieldname": "payment_request", "fieldtype": "Link", "options": "Payment Request", "width": 140},
        {"label": "Sales Invoice", "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
        {"label": "Sales Order", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
        {"label": "Gross Amount", "fieldname": "gross", "fieldtype": "Currency", "width": 120},
        {"label": "Merchant Fee", "fieldname": "merch_fee", "fieldtype": "Currency", "width": 120},
        {"label": "Net Amount", "fieldname": "net", "fieldtype": "Currency", "width": 120},
        {"label": "Transaction ID", "fieldname": "txn_id", "fieldtype": "Data", "width": 180},
    ]

    conditions = ""
    if from_date:
        conditions += " AND st.created >= %(from_date)s"
    if to_date:
        conditions += " AND st.created <= %(to_date)s"

    data = frappe.db.sql(f"""
        SELECT
            st.created,
            st.name AS charge_id,
            mp.available_on,
            mp.associated_payment_entry AS payment_entry,
            mp.associated_payment_request AS payment_request,
            mp.associated_sales_invoice AS sales_invoice,
            mp.associated_sales_order AS sales_order,
            mp.gross_amount AS gross,
            mp.merchant_fee AS merch_fee,
            mp.net_amount AS net,
            mp.merchant_transaction_id AS txn_id
        FROM `tabStripe Transaction` st
        JOIN `tabMerchant Payment` mp ON st.name = mp.source
        WHERE 1=1 {conditions}
        ORDER BY st.created DESC
    """, filters, as_dict=1)

    return columns, data
