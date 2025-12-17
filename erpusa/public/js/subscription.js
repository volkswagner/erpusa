const stripe_logo = `
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-stripe" viewBox="0 0 16 16">
        <path d="M2 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2zm6.226 5.385c-.584 0-.937.164-.937.593 0 .468.607.674 1.36.93 1.228.415 2.844.963 2.851 2.993C11.5 11.868 9.924 13 7.63 13a7.7 7.7 0 0 1-3.009-.626V9.758c.926.506 2.095.88 3.01.88.617 0 1.058-.165 1.058-.671 0-.518-.658-.755-1.453-1.041C6.026 8.49 4.5 7.94 4.5 6.11 4.5 4.165 5.988 3 8.226 3a7.3 7.3 0 0 1 2.734.505v2.583c-.838-.45-1.896-.703-2.734-.703"></path>
    </svg>
`

const stripe_subscription_status_color = {
    'Email Queued': 'blue',
    'Email Sent': 'blue',
    'Incomplete': 'yellow',
    'Incomplete Expired': 'red',
    'Trialing': 'green',
    'Active': 'green',
    'Past Due': 'red',
    'Canceled': 'orange',
    'Unpaid': 'red',
    'Paused': 'yellow'
}

let is_unlocked = false;
const autocharge_with_stripe_fields = [
    {
        "name": "generate_invoice_at",
        "value": "Beginning of the current subscription period"
    },
    {
        "name": "generate_new_invoices_past_due_date",
        "value": 1
    },
    {
        "name": "submit_invoice",
        "value": 1
    },
];

frappe.ui.form.on("Subscription", {
    setup: function (frm) {
        frm.set_query("user_account_representative", function (doc) {
			return {
				query: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_customer_contact",
				filters: {
					customer: doc.party,
				},
			};
		});
    },

    refresh: async function(frm) {
        if (frm.doc.status !== "Cancelled") {
            frm.remove_custom_button(__("Cancel Subscription"), __("Actions"));
			frm.add_custom_button(
				__("Cancel Subscription"),
				() => frm.trigger("cancel_subscription"),
				__("Actions")
			);
		}
        if (frm.doc.email_queue) {
            if (frm.doc.stripe_subscription_id) {
                displayIntro(frm, frm.doc.stripe_subscription_status)
            }
            else {
                frappe.call({
                    method: 'frappe.client.get',
                    args: {
                        doctype: 'Email Queue',
                        name: frm.doc.email_queue
                    },
                    callback: function (r) {
                        let additional_info = r.message.status == "Sent"? "Customer has been notified to set up a payment method." : "An email was scheduled to be sent to the customer.";
                        let status =  "Email " + r.message.status;
                        if (frm.doc.status == "Cancelled") {
                            additional_info = "Subscription was cancelled before customer could pay.";
                            status = "Canceled";
                        }

                        displayIntro(frm, status, additional_info);
                    }
                });
            }
            
            frappe.call({
                method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.email_queue_exists",
                args: {
                    email_queue: frm.doc.email_queue
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_df_property("email_queue", "description", 
                            `<small><a href=${r.message} target="_blank">Open Email Queue doc</a></small>`
                        )
                    }
                    else {
                        frm.set_df_property("email_queue", "description", "<small>Email Queue doc already deleted and can't be viewed.</small>")
                    }
                }
            });
        }

        if (frm.doc.stripe_subscription_id) {
            ["plans", "autocharge_with_stripe", "payment_gateway_account", "payment_method_configuration", "mode_of_payment"].forEach(function(field) {
                frm.set_df_property(field, "read_only", true);
            })

            frappe.call({
                method: "erpusa.stripe_plus.api.webhook_receiver_subscription.is_customer_user",
                args: {
                    representative: frm.doc.user_account_representative
                },
                callback: function (r) {
                    if (!r.message.user) {
                        frm.add_custom_button("Convert Customer to User", function() {
                            frappe.call({
                                method: "erpusa.stripe_plus.api.webhook_receiver_subscription.convert_customer_to_user",
                                freeze: true,
                                freeze_message: __("Converting Customer to User"),
                                args: {
                                    representative: frm.doc.user_account_representative,
                                    email_address: r.message.email_address,
                                    customer: frm.doc.party
                                },
                                callback: function (r) {
                                    if (!r.message) {
                                        frm.refresh();
                                    }
                                }
                            })
                        }, stripe_logo + __("Tools"))
                    }
                }
            })
        
            frm.add_custom_button("Look for Unallocated Stripe Transactions", function() {
                frappe.call({
                    method: "erpusa.stripe_plus.api.webhook_receiver_subscription.find_unallocated_payments",
                    freeze: true,
                    freeze_message: __("Finding Unallocated Payments"),
                    args: {
                        subscription_name: frm.doc.name,
                        customer_name: frm.doc.party,
                        stripe_subscription: frm.doc.stripe_subscription_id,
                        payment_gateway: frm.doc.payment_gateway
                    },
                    callback: function (r) {
                        if (r.message) {
                            let unallocated_payments_dialog = new frappe.ui.Dialog({
                                size: "extra-large",
                                title: "Unallocated Stripe Transactions",
                                fields: [
                                    {
                                        fieldname: 'instructions',
                                        fieldtype: 'HTML',
                                        options: `
                                            <p>The table below shows Stripe Transactions that don't have Payment Entries yet. Select the Stripe Transaction you'd like to allocate.</p>
                                            <p>
                                                <b>Note:</b> 
                                                <span>Payments will be automatically applied to any unpaid Sales Invoices. If there are none, an Advance Payment will be created instead.</span>
                                            </p>
                                        `
                                    },
                                    {
                                        fieldname: 'unallocated_stripe_transactions',
                                        fieldtype: 'Table',
                                        cannot_add_rows: 1,
                                        cannot_delete_rows: 1,
                                        in_place_edit: 0,
                                        data: r.message.unallocated_stripe_transactions,
                                        fields: [
                                            {
                                                fieldname: 'name',
                                                fieldtype: 'Link',
                                                label: 'Transaction',
                                                options: 'Stripe Transaction',
                                                read_only: 1,
                                                in_list_view: 1,
                                                columns: 4
                                            },
                                            {
                                                fieldname: 'amount',
                                                fieldtype: 'Currency',
                                                label: 'Amount',
                                                read_only: 1,
                                                in_list_view: 1,
                                                columns: 1
                                            },
                                            {
                                                fieldname: 'payment_method_type',
                                                fieldtype: 'Data',
                                                label: 'Payment Method',
                                                read_only: 1,
                                                in_list_view: 1,
                                                columns: 2
                                            },
                                            {
                                                fieldname: 'created',
                                                fieldtype: 'Datetime',
                                                label: 'Received',
                                                in_list_view: 1,
                                                read_only: 1,
                                                columns: 3
                                            }
                                        ]
                                    }
                                ]
                            });

                            if (r.message.unallocated_stripe_transactions.length > 0) {
                                unallocated_payments_dialog.set_primary_action("Allocate Payments", function() {
                                    frappe.call({
                                        method: "erpusa.stripe_plus.api.webhook_receiver_subscription.allocate_payments",
                                        freeze: true,
                                        freeze_message: __("Allocating Payments"),
                                        args: {
                                            subscription: frm.doc.name,
                                            stripe_transactions: r.message.unallocated_stripe_transactions,
                                            invoice_count: r.message.invoice_count,
                                            payment_gateway: frm.doc.payment_gateway
                                        },
                                        callback: function (r) {
                                            unallocated_payments_dialog.hide();
                                        }
                                    });
                                });
                            }

                            unallocated_payments_dialog.show();
                        }
                    }
                })
            }, stripe_logo + __("Tools"))

            frm.add_custom_button(__("Re-sync Subscription"), function() {
                frappe.call({
                    method: "erpusa.stripe_plus.api.webhook_receiver_subscription.resync_subscription",
                    freeze: true,
                    freeze_message: __("Re-syncing Subscription"),
                    args: {
                        subscription_name: frm.doc.name,
                        stripe_subscription_id: frm.doc.stripe_subscription_id,
                        payment_gateway: frm.doc.payment_gateway
                    },
                    callback: function (r) {
                        if (r.message) {
                            frm.refresh();
                        }
                    }
                })
            }, stripe_logo + __("Tools"))
            
            frm.add_custom_button(__("Unlock Fields"), function() {
                autocharge_with_stripe_fields.forEach(function(field) {
                    frm.set_df_property(field, "read_only", 0);
                    frm.set_df_property(
                        field,
                        "description",
                        null
                    );
                });
                
                frm.disable_save();

            }, stripe_logo + __("Tools"));
        }
        
        frm.events.toggle_autocharge_with_stripe_fields(frm);
        frm.events.toggle_stripe_plus_fields_reqd(frm);
        frm.events.insert_reload_button(frm);
        frm.events.insert_advance_payments_link(frm);
    },

    autocharge_with_stripe: function(frm) {
        frm.events.display_autocharge_notice(frm);
        frm.events.set_trial_end_date(frm);
        frm.events.toggle_stripe_plus_fields_reqd(frm);
    },

    party_type: function (frm) {
        if (frm.doc.party_type !== "Customer") {
            frm.set_value("autocharge_with_stripe", 0);
        }
    },

    party: function (frm) {
        frm.events.set_user_account_representative(frm);
    },

    mode_of_payment: function (frm) {
        frm.events.set_account_and_payment_gateway_account(frm);
    },

    start_date: function (frm) {
        frm.events.set_trial_end_date(frm);
    },

    trial_period_start: function (frm) {
        frm.events.set_trial_end_date(frm);
    },

    set_user_account_representative: function (frm) {
        if (frm.doc.autocharge_with_stripe && frm.doc.party) {
            frappe.call({
                method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_user_account_representative",
                args: {
                    customer: frm.doc.party
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("user_account_representative", r.message)
                    }
                }
            });
        }
    },
    
    set_account_and_payment_gateway_account: function (frm) {
        frappe.call({
            method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_bank_account_for_payment_request",
            args: {
                mode_of_payment: frm.doc.mode_of_payment,
                company: frm.doc.company
            },
            callback: function(r) {
                if (r.message) {
                    frm.set_value("account", r.message.account || null)
                    frm.set_value("payment_gateway_account", r.message.payment_gateway_account || null)
                }
            }
        });
    },

    set_subscription_fields: function (frm) {
        frm.events.toggle_autocharge_with_stripe_fields(frm);
        frm.set_value("generate_new_invoices_past_due_date", 1);
        frm.set_value("submit_invoice", 1);
        frm.set_value("generate_invoice_at", "Beginning of the current subscription period");
    },

    set_trial_end_date: function (frm) {
        if (frm.doc.autocharge_with_stripe && frm.doc.trial_period_start) {
            frm.set_df_property(
                "trial_period_end", 
                "description", 
                `<div class="alert alert-warning p-2 mt-2" role="alert">
                    <small>Field is locked to allow autocharging with Stripe.</small>
                </div>`
            );
            frm.set_df_property("trial_period_end", "read_only", 1);
            if (frm.doc.start_date) frm.set_value("trial_period_end", frappe.datetime.add_days(frm.doc.start_date, -1));
        }
    },

    cancel_subscription: function (frm) {
		cancel_subscription_dialog = frappe.confirm(
			__("This action will stop future billing. Are you sure you want to cancel this subscription?"),
			() => {
				frappe.call({
                    method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.cancel_subscription",
                    args: {
                        subscription_name: frm.doc.name
                    },
                    callback: function (r) {
                        if (!r.exec) {
                            frm.reload_doc();
                        }
                    }
                });
			},
		);
	},

    toggle_autocharge_with_stripe_fields: function (frm) {
        autocharge_with_stripe_fields.forEach(function(field) {
            frm.set_df_property(field.name, "read_only", frm.doc.autocharge_with_stripe);
            frm.set_df_property(
                field.name,
                "description",
                frm.doc.autocharge_with_stripe? renderFieldDescription(field.value) : null
            );
        });
    },

    toggle_stripe_plus_fields_reqd: function (frm) {
        ["mode_of_payment", "user_account_representative", "start_date"].forEach(
            (field) => frm.set_df_property(field, "reqd", frm.doc.autocharge_with_stripe)
        );
    },

    display_autocharge_notice: function (frm) {
        if (
            frm.doc.autocharge_with_stripe &&
            (frm.doc.generate_invoice_at != "Beginning of the current subscription period" ||
            frm.doc.generate_new_invoices_past_due_date != 1 ||
            frm.doc.submit_invoice != 1)
        ) {
            if (frm._toggled) {
                frm._toggled = false;
                return;
            }

            frappe.confirm(renderNoticeContent(autocharge_with_stripe_fields),
                () => {
                    frm.set_value("autocharge_with_stripe", 1);
                    frm.events.set_subscription_fields(frm);
                    frm.events.set_user_account_representative(frm);
                    frm._toggled = true;
                },
                () => {
                    frm.set_value("autocharge_with_stripe", 0)
                }
            )
            
        }
    }, 

    insert_reload_button: function (frm) {
        let reload_button = frm.add_custom_button("Reload Doc", function() {
            frappe.dom.freeze("Reloading Doc");

            frm.reload_doc().then(() => {
                frappe.dom.unfreeze();
            });
        });
        reload_button.html(`
            <svg class="es-icon es-line  icon-sm" style="" aria-hidden="true">
                <use class="" href="#es-line-reload"></use>
            </svg>
        `);
    },
    
    insert_advance_payments_link: function (frm) {
        if (frm.doc.party_type && frm.doc.party) {
            frappe.call({
                method: "erpusa.stripe_plus.api.webhook_receiver_subscription.find_advance_payments",
                args: {
                    customer: frm.doc.party
                },
                callback: function (r) {
                    if (r.message) {
                        let advance_payment_list = r.message
                        let payment_entry_node = $('.document-link[data-doctype="Payment Entry"]');

                        // Advance Payment Link is already inserted update the count instead
                        if (payment_entry_node.length == 0) {
                            let link = window.location.origin + "/app/payment-entry?status=Submitted&reference_no=%5B%22like%22%2C%22pi%25%22%5D&reference_name=%5B%22is%22%2C%22not+set%22%5D&party=" + encodeURI(frm.doc.party);
                            $('[data-page-route="Subscription"] .document-link[data-doctype="Sales Invoice"]').after(
                                $(`
                                    <div class="document-link" data-doctype="Payment Entry">
                                        <div class="document-link-badge" data-doctype="Payment Entry"> 
                                            <span class="count ${advance_payment_list.length == 0? "hidden" : ""}">${advance_payment_list.length}</span>
                                            <a class="badge-link" href="${link}" target="_blank">Advance Payment</a>
                                        </div> 
                                        <span class="open-notification hidden" title="Advance Payment"></span>
                                    </div>
                                `)
                            );
                        }
                        else {
                            payment_entry_node.find('.count').html(r.message.length);
                        }
                        // force the Advance Paymetn count to always show
                        if (advance_payment_list.length > 0)  payment_entry_node.find('.count').removeClass('hidden');
                       
                    }
                }
            });

        } 
    }
});

function renderFieldDescription(value) {
    let value_phrase = null;

    if (value == "1") {
        value_phrase = `checked`
    }
    else {
        value_phrase = `set to "${value}"`
    }

    return `
        <div class="alert alert-warning p-2 mt-2" role="alert">
            <small>Field is locked and ${value_phrase} to allow autocharging with Stripe.</small>
        </div>
    `
}

function renderNoticeContent(fields) {
    let table_content = 
    `<tr>
        <td><b>Field Name</b></td>
        <td><b>Field Value</b></td>
    <tr/>`

    fields.forEach((field) => {
        let field_name = frappe.utils.to_title_case(field.name.replaceAll("_", " "));
        let field_value = field.value;

        if (field_value == "1") {
            field_value = "Checked"
        }

        table_content = table_content + 
        `<tr>
            <td>${field_name}</td>
            <td>${field_value}</td>
        <tr/>`
    })

    return `
        <p>Enabling Stripe auto-charging will automatically set/override the fields below. Continue?</p>
        <table class="table table-bordered">
            ${table_content}
        </table>
    `
}

function displayIntro(frm, stripe_subscription_status, additional_info="") {
    frm.set_intro(__(
        `<div class="d-flex align-items-center" style="gap: 0.5rem;">
            ${stripe_logo}
            <b>Stripe Status: ${stripe_subscription_status}</b>${additional_info? " &bull; ": ""}<span>${additional_info}</span>
        </div>`
        
    ), stripe_subscription_status_color[stripe_subscription_status]);
}