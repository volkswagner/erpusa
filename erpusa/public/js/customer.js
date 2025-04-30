frappe.ui.form.on("Customer", {
    refresh: function(frm) {
        if (!frm.doc.stripe_customer_id) {
            frm.add_custom_button(__("Add Customer to Stripe"), function() {
                frappe.prompt({
                    label: 'Select Stripe Settings',
                    fieldname: 'stripe_settings',
                    fieldtype: 'Link',
                    options: 'Stripe Settings',
                    default: ""
                }, (values) => {
                    frappe.call({
                        method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.create_stripe_customer",
                        args: {
                            customer: frm.doc.name,
                            stripe_settings: values.stripe_settings,
                            show_success_message: 1
                        },
                        freeze: true,
                        freeze_message: __("Adding Customer to Stripe"),
                        callback: function(r) {
                        }
                    });
                })
            }, __("Actions"));
        }
    }
})