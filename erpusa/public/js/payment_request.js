frappe.ui.form.on("Payment Request", {
    setup: function (frm) {            
        frm.set_query("payment_method_configuration", function(doc) {
            return {
                query: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_payment_methods",
                filters: {"payment_gateway": doc.payment_gateway, "active": 1}
            };
        });
    },

    onload: function(frm) { 
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Stripe Plus Settings"
            },
            callback: function (r) {
                if (r.message) {
                    if (!r.message.enable_stripe_plus) {
                        if (!r.message.hide_warning) {
                            frm.set_intro(
                                __(`Stripe Plus is disabled. To use Stripe Plus' Payment Page, go to
                                    <span> 
                                        <a href=${frappe.utils.get_form_link("Stripe Plus Settings", "")} target="_blank">Stripe Plus Settings</a>
                                    </span> 
                                    and tick the 'Enable Stripe Plus' checkbox
                                `),
                                "yellow"
                            );
                        }
                    }
                    else {
                    }
                }
            }
        });

        toggle_stripe_plus_section(frm);

        toggle_do_not_create_invoice_checkbox(frm);
    },

    refresh: function(frm) {
        if (frm.doc.payment_url) {
            frm.add_custom_button("Preview Payment Page", function() {
                window.open(`${frm.doc.payment_url}&preview`, "_blank");
            }, "Tools")
        }
    },

    payment_gateway_account: function (frm) {
        frm.set_value("payment_method_configuration", null)
    },

    payment_method_configuration: function(frm) {
        if (frm.doc.payment_method_configuration && frm.doc.payment_gateway) {
            frappe.call({
                method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_pm_configuration_methods",
                args: {
                    payment_method_configuration: frm.doc.payment_method_configuration
                },
                callback: function(r) {
                    frm.set_value(
                        "methods_included",
                        r.message || null
                    )
                }
            })
        }
        else {
            frappe.call({
                method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_default_pm_configuration_methods",
                args: {
                    payment_gateway: frm.doc.payment_gateway
                },
                callback: function(r) {
                    frm.set_value(
                        "methods_included",
                        r.message || null
                    )
                }
            })
        }
    },

    payment_gateway: function(frm) {
        toggle_stripe_plus_section(frm);
    },

    mode_of_payment: function (frm) {
        set_bank_and_payment_gateway_accounts(frm)
    }
})

function toggle_stripe_plus_section(frm) {
    if (frm.doc.payment_gateway) {
        frappe.call({
            method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.is_stripe_plus_applicable",
            args: {
                payment_gateway: frm.doc.payment_gateway
            },
            callback: function (r) {
                frm.set_df_property("stripe_plus_section", "hidden", !(r.message));
                frm.set_df_property("is_a_subscription", "hidden", (r.message));
            }
        });
    }
    else {
        frm.set_df_property("is_a_subscription", "hidden", 0);
    }
}

function toggle_do_not_create_invoice_checkbox(frm) {
    frm.set_df_property("do_not_create_invoice", "hidden", !(frm.doc.reference_doctype && frm.doc.reference_doctype === "Sales Order"));
}

function set_bank_and_payment_gateway_accounts(frm) {
    frappe.call({
        method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_bank_account_for_payment_request",
        args: {
            mode_of_payment: frm.doc.mode_of_payment,
            company: frm.doc.company
        },
        callback: function(r) {
            if (r.message) {
                frm.set_value("bank_account", r.message.bank_account || null)
                frm.set_value("payment_gateway_account", r.message.payment_gateway_account || null)
            }
        }
    })
}