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
                        frm.set_df_property("stripe_plus_section", "hidden", 1)

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
                        frm.set_df_property("stripe_plus_section", "hidden", 0)

                    }
                }
            }
        });

        if (frm.doc.payment_gateway) {
            frm.set_query("payment_methods", function() {
                return {
                    query: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_payment_methods",
                    filters: {"payment_gateway": frm.doc.payment_gateway, "active": 1}
                };
            });
        }
        frm.add_custom_button("Pay", function() {
            frappe.call({
                method: "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
                args: {
                    dt: frm.doc.reference_doctype,
                    dn: frm.doc.reference_name,
                },
                callback: function (r) {
                    var doc = frappe.model.sync(r.message);
                    frappe.set_route("Form", doc[0].doctype, doc[0].name);
                },
            });
        });
    },

    payment_methods: function(frm) {
        if (frm.doc.payment_methods) {
            frappe.call({
                method: "frappe.client.get",
                args: {
                    doctype: "Stripe Payment Method Configuration",
                    name: frm.doc.payment_methods
                },
                callback: function(r) {
                    let list = "";
                    if (r.message.card) list += `<span class="pill text-white mr-2">Card Payments</span>`;
                    if (r.message.ach_debit_card) list += `<span class="pill text-white mr-2">ACH Debit Card</span>`;
    
                    frm.set_value(
                        "methods_included",
                        `
                        <div class="w-100 d-flex align-items-center justify-content-start p-0 m-0">
                            ${list}
                        </div>
                        `
                    )
                }
            })
        }
        else {
            frm.set_value("methods_included","")
        }
    },

    use_default_methods: function(frm) {
        if (frm.doc.use_default_methods) {
            frappe.call({
                method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_default_pm_configuration",
                args: {
                    payment_gateway: frm.doc.payment_gateway
                },
                callback: function(r) {
                    let list = "";
                    r.message.forEach(function(method) {
                        list += `<span class="pill text-white mr-2">${method}</span>`;
                    })
    
                    frm.set_value(
                        "methods_included",
                        `
                        <div class="w-100 d-flex align-items-center justify-content-start p-0 m-0">
                            ${list}
                        </div>
                        `
                    )
                }
            });
        }
        else {
            frm.set_value("methods_included", "");
        }
        frm.set_value("payment_methods", null);
    },

    party: function(frm) {
        if (frm.doc.party && frm.doc.party_type == "Customer" && !frm.doc.payment_methods) {
            frappe.call({
                method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.find_customer_configuration",
                args: {
                    customer: frm.doc.party
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value('use_default_methods', 0);
                        frm.set_value('payment_methods', r.message.configuration);
                    }
                }
            });
        }
        else {
            frm.set_value('payment_methods', null);
        }
    }
})