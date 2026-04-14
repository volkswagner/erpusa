// Copyright (c) 2025, VolksWagner and contributors
// For license information, please see license.txt

frappe.ui.form.on("Merchant Payment", {
	refresh(frm) {
      frm.set_intro(
         __("Notice: Card and online payments are processed instantly, while ACH Debit Cards (us_bank_account) may take 3-5 business days."), "yellow"
      )
	},
});
