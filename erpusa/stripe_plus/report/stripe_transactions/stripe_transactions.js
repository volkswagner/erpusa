// Copyright (c) 2025, VolksWagner and contributors
// For license information, please see license.txt

// erpusa/stripe_plus/report/stripe_transactions_report/stripe_transactions_report.js

frappe.query_reports["Stripe Transactions"] = {
    "filters": [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.add_days(frappe.datetime.nowdate(), -1)
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.nowdate()
        }
    ]
};
