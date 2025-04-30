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
    }
});

frappe.ui.form.on('Stripe Notification Schedule', {
});
