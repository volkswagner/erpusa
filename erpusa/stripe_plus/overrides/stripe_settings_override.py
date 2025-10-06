import frappe

from urllib.parse import urlencode
from payments.payment_gateways.doctype.stripe_settings.stripe_settings import StripeSettings
from frappe.utils import get_url

class StripeSettingsOverride(StripeSettings):
    def get_payment_url(self, **kwargs):
        if frappe.db.get_single_value("Stripe Plus Settings", "enable_stripe_plus"):
            #return get_url(f"./stripe_plus_checkout?{urlencode(kwargs)}")
            minimalArgs = [("reference_doctype", kwargs["reference_doctype"]),
                           ("reference_docname", kwargs["reference_docname"]),
                           ("payment_gateway", kwargs["payment_gateway"]),
                           ("description", kwargs["description"])]
            return get_url(f"./stripe_plus_checkout?{urlencode(minimalArgs)}")
        else:
            return get_url(f"./stripe_checkout?{urlencode(kwargs)}")