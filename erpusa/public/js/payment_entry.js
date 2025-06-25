frappe.ui.form.on("Payment Entry", {
    refresh: function(frm) {
        if (frm.doc.paid_to) set_bank_account(frm, true)
    },
    mode_of_payment: function(frm) {
        if (frm.doc.paid_to) set_bank_account(frm, true)
    },
    paid_to: function(frm) {
        if (frm.doc.paid_to) set_bank_account(frm, true)
    },
    paid_from: function(frm) {
        if (frm.doc.paid_from) set_bank_account(frm, true)
    }
})

function set_bank_account(frm, trigger_change) {
    frappe.call({
        method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_bank_account_for_payment_entry",
        args: {
            payment_type: frm.doc.payment_type,
            paid_to: frm.doc.paid_to? frm.doc.paid_to : "",
            paid_from: frm.doc.paid_from? frm.doc.paid_from : "",
            trigger_change: trigger_change
        },
        callback: function(r) {
            if (r.message && r.message.bank_account) {
                frm.set_value("bank_account", r.message.bank_account)
            }
            else {
                frm.set_value("bank_account", null)
            }
        }
    })
}