// Copyright (c) 2025, VolksWagner and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Stripe Payment Method Configuration", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Stripe Payment Method Configuration", {
    refresh: function (frm) {
        if (frm.doc.stripe_configuration_id) {
            frm.add_custom_button(__("Resync with Stripe"), function() {
                frm.call({
                    method: "resync_payment_method_configuration",
                    freeze: true,
                    freeze_message: __("Resyncing"),
                    args: { 
                        configuration_name: frm.doc.name, 
                        stripe_configuration_id: frm.doc.stripe_configuration_id, 
                        stripe_settings: frm.doc.stripe_settings
                    },
                    callback: function (r) {
                        if (r.message) {
                            frm.reload_doc()
                        }
                    }
                });
            });
        }
    }
});