# Copyright (c) 2025, VolksWagner and contributors
# For license information, please see license.txt

import frappe
import time
from frappe.model.document import Document


class StripeLog(Document):
	def after_insert(self):
		pass