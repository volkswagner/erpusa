# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
import time
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import Interval
from frappe.query_builder.functions import Now
from frappe.utils import now_datetime, add_days


class StripeLog(Document):
	@staticmethod
	def clear_old_logs(days=365):
		stripe_log_table = frappe.qb.DocType("Stripe Log")
		cutoff_date = add_days(now_datetime(), -days)

		logs_to_delete = frappe.get_all(
			"Stripe Log",
			filters={"modified": [">", cutoff_date]},
			pluck="name"
		)

		stripe_transactions_affected = frappe.get_all(
			"Stripe Transaction Data Source",
			filters={"stripe_log": ["in", logs_to_delete]},
			pluck="parent"
		)

		for stripe_transaction in stripe_transactions_affected:
			st_doc = frappe.get_doc("Stripe Transaction", stripe_transaction)
			st_doc.data_source = []

			try:
				st_doc.save()

			except Exception as e:
				frappe.log_error(str(e), _("Failed clearing update history of {}").format(stripe_transaction))

		frappe.db.delete(stripe_log_table, filters=(stripe_log_table.modified < (Now() - Interval(days=days))))
