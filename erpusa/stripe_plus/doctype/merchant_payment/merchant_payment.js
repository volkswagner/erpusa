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
            if (!frm.doc.associated_payment_entry) {
                  frm.add_custom_button(__("Retry PE"), function() { 
                        frm.call({
                              method: "retry_payment_entry",
                              doc: frm.doc
                        }).then((response) => {
                              frm.reload_doc().then(() => {
                                    console.log(response.message && response.message.success_message)
                                    if (response.message && response.message.success_message)  {
                                          frappe.msgprint({
                                                title: __("Payment Entry Creation Successful"),
                                                message: response.message.success_message
                                          });
                                    }
                              });
                        });
                  });
                  $('[data-label="Retry%20PE"]')
                  .attr("title", "Retry Payment Entry")
                  .attr("data-toggle", "tooltip")
                  .tooltip();
            }
      }
});
