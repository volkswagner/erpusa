// Copyright (c) 2025, VolksWagner and contributors
// For license information, please see license.txt

const states = {
      'Pending': "blue",
      'Available': "green",
      'Failed': "red"
}

frappe.ui.form.on("Merchant Payment", {
	refresh(frm) {
            frm.set_intro(
            __("Notice: Card and online payments are processed instantly, while ACH Debit Cards (us_bank_account) may take 3-5 business days."), "yellow"
            )
            frm.events.add_retry_pe_button(frm);
	},

      add_retry_pe_button(frm) {
            if (!frm.is_new() && !frm.doc.associated_payment_entry) {
                  const retry_pe = () => {
                        frm.call({
                              method: "retry_payment_entry",
                              freeze: true,
                              freeze_message: __("Retrying PE"),
                              doc: frm.doc
                        }).then((response) => {
                              frm.reload_doc().then(() => {
                                    if (response.message && response.message.success_message)  {
                                          frappe.msgprint({
                                                title: __("Payment Entry Creation Successful"),
                                                message: response.message.success_message
                                          });
                                    }
                              });
                        });
                  }
                  
                  frm.add_custom_button(__("Retry PE"), function() { 
                        if (frm.doc.associated_subscription) {
                              frappe.confirm(
                                    __("This feature is not ideal for subscription payments. Retry PE anyways?"),
                                    () => { retry_pe(); },
                                    () => {}
                              );
                        }

                        else {
                              retry_pe();
                        }
                  });
                  $('[data-label="Retry%20PE"]')
                  .attr("title", "Retry Payment Entry")
                  .attr("data-toggle", "tooltip")
                  .tooltip();
            }
      }
});
