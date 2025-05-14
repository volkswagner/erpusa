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
    },
    fetch_bank_accounts: function(frm) {
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Bank Account"
            },
            callback: function(r) {
                if (r.message) {
                    console.log(r.message)
                }
            }
        })
    }
});

frappe.ui.form.on('Stripe Plus Settings Notification Schedule', {
});
