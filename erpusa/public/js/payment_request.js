frappe.ui.form.on("Payment Request", {
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

        if (frm.doc.payment_gateway) {
            frm.set_query("payment_methods", function() {
                return {
                    query: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_payment_methods",
                    filters: {"payment_gateway": frm.doc.payment_gateway, "active": 1}
                };
            });
        }
    },

    refresh: function(frm) {
        if (frm.doc.payment_url) {
            frm.add_custom_button("Open Payment Page", function() {
                window.open(frm.doc.payment_url, "_blank");
            }, "Tools")
        }
    },

    payment_method_configuration: function(frm) {
        if (frm.doc.payment_method_configuration && frm.doc.payment_gateway) {
            frappe.call({
                method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_pm_configuration_methods",
                args: {
                    payment_method_configuration: frm.doc.payment_method_configuration
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value(
                            "methods_included",
                            r.message
                        )
                    }
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
                    if (r.message) {
                        frm.set_value(
                            "methods_included",
                            r.message
                        )
                    }
                }
            })
        }
    },

    payment_gateway: function(frm) {
        toggle_stripe_plus_section(frm);
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
                if (r.message) {
                    frm.set_df_property("stripe_plus_section", "hidden", 0);
                }
                else
                {
                    frm.set_df_property("stripe_plus_section", "hidden", 1);
                }
            }
        });
    }
}

function toggle_do_not_create_invoice_checkbox(frm) {
    if (frm.doc.reference_doctype && frm.doc.reference_doctype === "Sales Order") {
        frm.set_df_property("do_not_create_invoice", "hidden", 0);
    }
    else {
        frm.set_df_property("do_not_create_invoice", "hidden", 1);
    }
}