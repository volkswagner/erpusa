frappe.ui.form.on("Auto Repeat", {
    setup: function (frm) {
        frm.set_query("payment_method_configuration", function(doc) {
            return {
                query: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_payment_methods",
                filters: {"payment_gateway": doc.payment_gateway, "active": 1}
            };
        });
    },

    refresh: function (frm) {
        toggle_notification_section(frm.doc.send_payment_request_instead && frm.doc.notify_by_email);
    },

    send_payment_request_instead: function (frm) {
        if (frm.doc.send_payment_request_instead) {
            frm.set_value("submit_on_creation", 1);
            frm.set_value("notify_by_email", 1);
            if (!frm.doc.reference_document) {
                frm.call("fetch_linked_contacts");
            }

            frappe.after_ajax(function () {
                toggle_notification_section(true);
            })
        }

        else {
            frm.set_value("submit_on_creation", 0);
            frm.set_value("notify_by_email", 0);
            frappe.after_ajax(function () {
                toggle_notification_section(false);
            })
        }

        
    },

    payment_gateway_account: function (frm) {
        if (frm.doc.payment_gateway_account && frm.doc.send_payment_request_instead) {
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Payment Gateway Account",
                    name: frm.doc.payment_gateway_account
                },
                callback: function (r) {
                    frm.set_value("message", r.message.message || 0)
                }
            })
        }
    },

    mode_of_payment: function (frm) {
        set_bank_and_payment_gateway_accounts(frm)
    }
})

function set_bank_and_payment_gateway_accounts(frm) {
    frappe.call({
        method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_bank_account_for_payment_request",
        args: {
            mode_of_payment: frm.doc.mode_of_payment,
            reference_doctype: frm.doc.reference_doctype,
            reference_docname: frm.doc.reference_document
        },
        callback: function(r) {
            if (r.message && ["Sales Order", "Sales Invoice"].includes(frm.doc.reference_doctype)) {
                frm.set_value("payment_gateway_account", r.message.payment_gateway_account || null)
            }
        }
    })
}


function toggle_notification_section(show) {
    $('div[data-fieldname="notification"]').each(function() {
        const section = $(this);
        const accordion_head = section.find('.section-head').first();
        const accordion_icon = section.find('use').first();
        const accordion_body = section.find('.section-body').first();

        if (section && accordion_head && accordion_body) {
            if (show) {
                accordion_head.removeClass("collapsed");
                accordion_body.removeClass("hide");
                accordion_icon.attr("href", "#es-line-up");
            }
            else {
                accordion_head.addClass("collapsed");
                accordion_body.addClass("hide");
                accordion_icon.attr("href", "#es-line-down");
            }
        }
    });
}