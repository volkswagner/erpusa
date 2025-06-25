import frappe

from erpnext.accounts.doctype.payment_request.payment_request import PaymentRequest
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import is_stripe_plus_applicable
from frappe.utils.background_jobs import enqueue

class PaymentRequestOverride(PaymentRequest):
    def get_payment_url(self):
        gateway_settings_doctype = frappe.db.get_value("Payment Gateway", self.payment_gateway, "gateway_settings")
        
        if frappe.get_doc("DocType", gateway_settings_doctype).custom:
            return None
        
        return super().get_payment_url()