// Copyright (c) 2025, VolksWagner and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Stripe Payment Method Configuration", {
// 	refresh(frm) {

// 	},
// });
frappe.listview_settings['Stripe Payment Method Configuration'] = {
    refresh: function(listview) {
        listview.page.add_inner_button(__('My Custom Button'), function() {
            frappe.msgprint('Button clicked!');
            // Or run a server-side method, redirect, etc.
        });
    }
};