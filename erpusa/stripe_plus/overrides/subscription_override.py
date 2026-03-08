import frappe

from erpnext.accounts.doctype.subscription.subscription import Subscription
from erpnext.accounts.doctype.subscription.subscription import DateTimeLikeObject
from erpusa.stripe_plus.api.webhook_receiver_subscription import cancel_stripe_subscription

class SubscriptionOverride(Subscription):
    def create_invoice(
            self,
            from_date: DateTimeLikeObject | None = None,
            to_date: DateTimeLikeObject | None = None,
            posting_date: DateTimeLikeObject | None = None,
        ):
        if self.autocharge_with_stripe and frappe.db.get_single_value("Stripe Plus Settings", "automatically_apply_advance_payments"):
            # store original submit_invoice setting
            original_submit_invoice = self.submit_invoice

            # set to False to prevent invoice from original method from submitting
            self.submit_invoice = 0

            # create invoice and set submit_invoice again
            invoice = super().create_invoice()
            invoice.allocate_advances_automatically = 1
            invoice.set_missing_values()
            invoice.save()
            self.submit_invoice = original_submit_invoice
            
            if original_submit_invoice:
                invoice.submit()

            return invoice
        else:
            super().create_invoice()

    @frappe.whitelist()
    def cancel_subscription(self):
        super().cancel_subscription()
        cancel_stripe_subscription(self)
        
    @frappe.whitelist()
    def process(self, posting_date: DateTimeLikeObject | None = None) -> bool:
        previous_status = self.status
        super().process(posting_date)

        if previous_status != self.status and self.status in ("Completed", "Cancelled"):
            cancel_stripe_subscription(self)


