import frappe

from erpnext.accounts.doctype.subscription.subscription import Subscription
from erpnext.accounts.doctype.subscription.subscription import DateTimeLikeObject

class SubscriptionOverride(Subscription):
    def create_invoice(
            self,
            from_date: DateTimeLikeObject | None = None,
            to_date: DateTimeLikeObject | None = None,
            posting_date: DateTimeLikeObject | None = None,
        ):
        if self.autocharge_with_stripe and frappe.db.get_single_value("Stripe Plus Settings", "automatically_apply_advance_payments"):
            original_submit_invoice = self.submit_invoice

            self.submit_invoice = 0

            invoice = super().create_invoice()
            invoice.allocate_advances_automatically = 1
            invoice.set_missing_values()
            invoice.save()
            
            if original_submit_invoice:
                invoice.submit()

            return invoice
        else:
            super().create_invoice()