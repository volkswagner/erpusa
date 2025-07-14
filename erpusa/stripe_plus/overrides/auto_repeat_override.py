import frappe

from frappe.automation.doctype.auto_repeat.auto_repeat import AutoRepeat

class AutoRepeatOverride(AutoRepeat):
    def create_documents(self):
        from erpnext.accounts.doctype.payment_request.payment_request import make_payment_request

        if self.reference_doctype in ["Sales Invoice", "Sales Order", "Purchase Order", "Purchase Invoice"]:
            try:
                new_doc = self.make_new_document()
                    
            except Exception:
                error_log = self.log_error("Auto repeat failed")

                self.disable_auto_repeat()

                if self.reference_document and not frappe.flags.in_test:
                    self.notify_error_to_user(error_log)
            
            if self.reference_doctype in ["Sales Invoice", "Sales Order"]:
                party_type = "Customer"
                party = new_doc.customer
                party_name = frappe.db.get_value("Customer", new_doc.customer, "customer_name")
                payment_gateway_account = self.payment_gateway_account or None
                payment_gateway = self.payment_gateway or None
                payment_method_configuration = self.payment_method_configuration or None
                
            else:
                party_type = "Supplier"
                party = new_doc.supplier
                party_name = frappe.db.get_value("Supplier", new_doc.supplier, "supplier_name")
                payment_gateway_account = None
                payment_gateway = None
                payment_method_configuration = None
                
            try:
                pr_doc = make_payment_request(**{
                    'dt': self.reference_doctype,
                    'dn': new_doc.name,
                    'order_type': new_doc.get("order_type"),
                    'party_type': party_type,
                    'party': party,
                    'party_name': party_name,
                    'mode_of_payment': self.mode_of_payment or None,
                    'recipient_id': self.recipients,
                    'loyalty_points': new_doc.get("loyalty_points"),
                    'submit_doc': False,
                    'return_doc': True
                })
                
                pr_doc.message = self.message
                pr_doc.payment_gateway_account = payment_gateway_account
                pr_doc.payment_gateway = payment_gateway
                pr_doc.payment_method_configuration = payment_method_configuration
                    
                pr_doc.save()
            
            except Exception as e:
                error_log = self.log_error("Auto repeat failed to create payment_request", e)
            
            pr_doc.submit()
        else:
            super().create_documents()