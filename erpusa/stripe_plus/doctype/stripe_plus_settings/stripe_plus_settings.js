// Copyright (c) 2025, VolksWagner and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stripe Plus Settings", {
    onload: function(frm) {
        if (!frm.doc.notification_schedule || frm.doc.notification_schedule.length === 0) {
            frm.add_child('notification_schedule', {
                label: 'Noon',
                time: '12:00:00'
            })
            frm.add_child('notification_schedule', {
                label: 'Evening',
                time: '20:00:00'
            })
            frm.refresh_field('notification_schedule')
            
            frappe.call({
                method: "frappe.client.save",
                args: {
                    doc: frm.doc
                },
                freeze: false,
                show_alert: false,
                callback: function(r) {
                    if (!r.exc) {
                        frm.reload_doc()
                        frm.set_intro('')
                    }
                }
            });
        }
    },

    refresh: function(frm) {
        frm.set_query('user_to_authorize', function() {
            return {
              query: 'erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_users_with_write_access',
            };
        });

        $('button[data-fieldname="verify"]').addClass("btn-primary")
    },
});

frappe.ui.form.on('Stripe Plus Settings Webhook Validator', {
    verify: function(frm, cdt, cdn) {
        // cdt = Child DocType
        // cdn = Child DocType name (row ID)

        const row = locals[cdt][cdn];

        console.log('Row data:', row);
        console.log('Parent doc:', frm.doc);

        frappe.call({
            method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.verify_validator",
            args: {
                validator_name: row.name,
            },
            callback: function (r) {

            }
        })

    }
});
