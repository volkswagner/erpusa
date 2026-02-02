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

const tools_button = `${stripe_logo} Tools`

let currently_editing = null;


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
        frm.events.override_actions_buttons(frm);
        frm.events.set_intro(frm);
        frm.events.insert_look_for_unallocated_stripe_transactions_button(frm);
        frm.events.insert_advance_payments_link(frm);
        frm.events.insert_update_subscription(frm);
        frm.events.toggle_customer_conversion_notice_and_button(frm);
        frm.events.toggle_autocharge_with_stripe_fields(frm);
        frm.events.toggle_stripe_plus_fields_reqd(frm);
        frm.events.toggle_email_queue_link(frm);
        insertReloadButton(frm);
    },

    autocharge_with_stripe: function(frm) {
        frm.events.set_user_account_representative(frm);
        frm.events.set_subscription_fields(frm);
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

    override_actions_buttons: function (frm) {
        if (!frm.is_new() && frm.doc.email_queue) {
            if (frm.doc.status !== "Cancelled") {
                frm.remove_custom_button(__("Cancel Subscription"), __("Actions"));
                frm.add_custom_button(
                    __("Cancel Subscription"),
                    () => frm.events.cancel_subscription(frm),
                    __("Actions")
                );
            }
            else {
                frm.remove_custom_button(__("Restart Subscription"), __("Actions"));
                frm.add_custom_button(
                    __("Restart Subscription"),
                    () => frm.events.restart_subscription(frm),
                    __("Actions")
                );
            }
        }
    },

    set_intro: function (frm) {
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
        }
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
        ["user_account_representative", "start_date"].forEach(
            (field) => frm.set_df_property(field, "reqd", frm.doc.autocharge_with_stripe)
        );
    },

    cancel_subscription: function (frm, approval_dialog=null) {
        function cancel_now() {
            frappe.call({
                method: "erpusa.stripe_plus.api.webhook_receiver_subscription.cancel_subscription",
                freeze: !approval_dialog,
                freeze_message: __("Cancelling Subscription"),
                args: {
                    subscription_name: frm.doc.name
                },
                callback: function (r) {
                    if (!r.exec) {
                        frm.reload_doc();
                        frappe.show_alert({
                            message: __("Successfully Cancelled Subscription"),
                            indicator: "green"
                        });
                    }
                }
            });
        }

        frappe.confirm(
            __("This action will stop future billing. Are you sure you want to cancel this subscription?"),
            () => {
                if (approval_dialog) {
                    approval_dialog(cancel_now);
                }
                else {
                    cancel_now()
                }
            },
        );
	},

    restart_subscription: function (frm, new_start_date=null, new_end_date=null, approval_dialog=null) {
        let current_start_date = frm.doc.start_date? __("Current Start Date: ") + frm.doc.start_date : "Defaults to today";
        let current_end_date = frm.doc.start_date? __("Current End Date: ") + frm.doc.end_date : "";
        let request_new_start_date = new_start_date? " | " + __("Request Start Date: ") + new_start_date : "";
        let request_new_end_date = new_end_date? " | " + __("Request End Date: ") + new_end_date : "";

        function renew_now(values) {
            frappe.call({
                method: "erpusa.stripe_plus.api.webhook_receiver_subscription.renew_subscription",
                freeze: !approval_dialog,
                freeze_message: __("Renewing Subscription"),
                args: {
                    subscription_name: frm.doc.name,
                    new_start_date: values.new_start_date,
                    new_end_date: values.new_end_date,
                    autocharge_with_stripe: values.autocharge_with_stripe,
                    mode_of_payment: values.mode_of_payment,
                    payment_method_configuration: values.payment_method_configuration,
                    company: frm.doc.company
                },
                callback: function (r) {
                    if (!r.exec) {
                        renew_dialog.hide();
                        frm.reload_doc();
                        frappe.show_alert({
                            message: __("Successfully Renewed Subscription"),
                            indicator: "green"
                        });
                    }
                }
            });
        }

        let renew_dialog = new frappe.ui.Dialog({
            title: __("Confirm"),
            fields: [
                {
                    fieldtype: "HTML",
                    options: "<p>" + __("You are about to restart this subscription. You may set new settings for the renewal:") + "</p>"
                },
                {
                    fieldname: "new_start_date",
                    fieldtype: "Date",
                    label: "New Start Date",
                    default: new_start_date || frm.doc.start_date || frappe.datetime.get_today(),
                    reqd: 1,
                    description: "<small>" + current_start_date + request_new_start_date + "</small>"
                },
                {
                    fieldname: "new_end_date",
                    fieldtype: "Date",
                    label: "New End Date",
                    default: new_end_date|| frm.doc.end_date,
                    description: "<small>" + current_end_date + request_new_end_date + "</small>"
                },
                {
                    fieldname: "autocharge_with_stripe",
                    fieldtype: "Check",
                    label: "Autocharge with Stripe",
                    default: frm.doc.autocharge_with_stripe,
                    description: "<small>" + __("Current Value: ") + (frm.doc.autocharge_with_stripe? __("Checked") : __("Unchecked")) + "</small>"
                },
                {
                    fieldname: "mode_of_payment",
                    fieldtype: "Link",
                    label: "Mode of Payment",
                    options: "Mode of Payment",
                    default: frm.doc.mode_of_payment,
                    depends_on: "eval: doc.autocharge_with_stripe",
                    description: "<small>" + __("Current Value: ") + frm.doc.mode_of_payment + "</small>"
                },
                {
                    fieldname: "payment_method_configuration",
                    fieldtype: "Link",
                    label: "Payment Method Configuration",
                    options: "Stripe Payment Method Configuration",
                    default: frm.doc.payment_method_configuration,
                    depends_on: "eval: doc.autocharge_with_stripe",
                    description: "<small>" + __("Current Value: ") + (frm.doc.payment_method_configuration || "None") + "</small>"
                }
            ],
            primary_action_label: __("Yes"),
            primary_action: function (values) {
                if (approval_dialog) {
                    approval_dialog(renew_now, values)
                }
                else {
                    renew_now(values);
                }
            },
            secondary_action_label: __("No"),
            secondary_action: function () {
                renew_dialog.hide();
            }
        });

        renew_dialog.show();
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
    },

    toggle_customer_conversion_notice_and_button: function (frm) {
        if (frm.doc.stripe_subscription_id) {
            frappe.call({
                method: "erpusa.stripe_plus.api.webhook_receiver_subscription.is_customer_user",
                args: {
                    representative: frm.doc.user_account_representative
                },
                callback: function (r) {
                    if (!r.message.user) {
                        frm.add_custom_button("Grant Access to Portal Page", function() {
                            frappe.call({
                                method: "erpusa.stripe_plus.api.webhook_receiver_subscription.convert_customer_to_user",
                                freeze: true,
                                freeze_message: __("Granting Portal Page Access"),
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
                        }, tools_button);

                        frm.set_df_property(
                            "user_account_representative",
                            "description",
                            `<div class="alert alert-warning p-2 mt-2" role="alert">
                                <small>Customer doesn't have access to the portal page and won't be able to manage their Subscriptions. Grant access by clicking on <i>Tools > Grant Access to Portal Page</i>.</small>
                            </div>`
                        );
                    }
                    frm.set_df_property(
                        "user_account_representative",
                        "description",
                        null
                    );
                }
            })
        }
        else {
            frm.set_df_property(
                "user_account_representative",
                "description",
                null
            );
        }
    },

    insert_look_for_unallocated_stripe_transactions_button: function (frm) {
        if (frm.doc.stripe_subscription_id) {
            ["autocharge_with_stripe", "payment_gateway_account", "payment_method_configuration", "plans"].forEach(function(field) {
                frm.set_df_property(field, "read_only", true);
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
            }, tools_button)

        }
    },

    insert_update_subscription: function (frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(
                __("Apply an Update Request"),
                function () {
                    frappe.call({
                        method: "erpusa.stripe_plus.api.webhook_receiver_subscription.fetch_subscription_update_requests",
                        args: {
                            subscription: frm.doc.name
                        },
                        callback: function (r) {
                            if (r.message) {
                                let update_request_select_dialog = new frappe.ui.Dialog({
                                    title: __("Choose an Update Request to Apply"),
                                    size: "extra-large",
                                    fields: [
                                        {
                                            fieldtype: "HTML",
                                            options: `<p>${__("Select an update request from the table below. Click the 'Apply Update/s from Request' button to automatically apply the changes requested by the customer.")}</p>`
                                        },
                                        {
                                            fieldtype: "Table",
                                            fieldname: "update_requests",
                                            cannot_add_rows: 1,
                                            cannot_delete_rows: 1,
                                            in_place_edit: 0,
                                            fields: [
                                                {
                                                    fieldname: "name",
                                                    fieldtype: "Link",
                                                    label: "Request ID",
                                                    options: "Subscription Update Request",
                                                    in_list_view: 1,
                                                    read_only: 1,
                                                    columns: 2
                                                },
                                                {
                                                    fieldname: "creation",
                                                    fieldtype: "Datetime",
                                                    label: "Date Requested",
                                                    in_list_view: 1,
                                                    read_only: 1,
                                                    columns: 2
                                                },
                                                {
                                                    fieldname: "request_type",
                                                    fieldtype: "Data",
                                                    label: "Type",
                                                    in_list_view: 1,
                                                    read_only: 1,
                                                    columns: 2
                                                },
                                                {
                                                    fieldname: "details",
                                                    fieldtype: "Long Text",
                                                    label: "Request Details",
                                                    in_list_view: 1,
                                                    read_only: 1,
                                                    columns: 3
                                                },
                                                {
                                                    fieldname: "additional_information",
                                                    fieldtype: "Long Text",
                                                    label: "Customer Notes",
                                                    in_list_view: 1,
                                                    read_only: 1,
                                                    columns: 1
                                                }
                                            ],
                                            data: r.message
                                        }
                                    ]
                                });

                                update_request_select_dialog.set_primary_action(
                                    __("Apply Update/s from Request"),
                                    function () {
                                        update_request_select_dialog.hide();

                                        let selected_rows = update_request_select_dialog.get_values().update_requests;
                                        let selected_row_count = selected_rows.filter(row => row.__checked === 1).length;
                                        let selected = selected_rows[0];
                                        let request_type = selected.request_type;

                                        if (selected_row_count === 0) frappe.throw(__("Select a request."));

                                        if (selected_row_count > 1) frappe.throw(__("You can only apply a request one at a time."));

                                        let approve_update_request_dialog = null;

                                        function displayApproveRequestDialog (run_after=null, args=null) {
                                            if (!approve_update_request_dialog) {
                                                approve_update_request_dialog = frappe.prompt([
                                                    {
                                                        fieldname: "name",
                                                        fieldtype: "Data",
                                                        label: "Request ID",
                                                        read_only: 1,
                                                        default: selected_rows[0].name
                                                    },
                                                    {
                                                        fieldname: "status",
                                                        fieldtype: "Data",
                                                        label: "Status",
                                                        read_only: 1,
                                                        default: "Approved"
                                                    },
                                                    {
                                                        fieldname: "notes",
                                                        fieldtype: "Long Text",
                                                        label: "Notes",
                                                    },
                                                ], (values) => {
                                                    if (run_after) {
                                                        frappe.call({
                                                            method: "erpusa.stripe_plus.api.webhook_receiver_subscription.approve_update_request",
                                                            args: {
                                                                update_request_name: values.name,
                                                                notes: values.notes 
                                                            },
                                                            callback: function (r) {
                                                                if (!r.exec) {
                                                                    if (args) {
                                                                        run_after(args);
                                                                    }
                                                                    else {
                                                                        run_after();
                                                                    }
                                                                }
                                                            }
                                                        });
                                                    }
                                                    else {
                                                        frappe.call({
                                                            method: "erpusa.stripe_plus.api.webhook_receiver_subscription.update_subscription",
                                                            freeze: true,
                                                            freeze_message: __("Approving Request"),
                                                            args: {
                                                                subscription_name: frm.doc.name,
                                                                payment_gateway: frm.doc.payment_gateway,
                                                                stripe_subscription_id: frm.doc.stripe_subscription_id,
                                                                update_request_name: values.name,
                                                                notes: values.notes 
                                                            },
                                                            callback: function (r) {
                                                                if (!r.exec) {
                                                                    frm.reload_doc();
                                                                }
                                                            }
                                                        });
                                                    }
                                                    
                                                });
                                            }
                                            else {
                                                approve_update_request_dialog.show();
                                            }

                                        }

                                        if (!["Cancellation", "Resubscription"].includes(request_type)) {
                                            let changes = selected.to_change;
                                            changes.forEach(function (change) {
                                                if (Array.isArray(change.new_value)) {
                                                    change.new_value.forEach(function (nv) {
                                                        let fieldname = change.fieldname;
                                                        let plan_index = frm.doc[fieldname].findIndex(plan => plan.name === nv.plan_id);
                                                        frm.doc[fieldname][plan_index].qty = nv.new_qty;
                                                    })
                                                }
                                                else {
                                                    frm.set_value(change.fieldname, change.new_value);
                                                }
                                                frm.refresh_field(change.fieldname);
                                            });
                                            
                                            changes.forEach(function (change, index) {
                                                setTimeout(() => {
                                                    frm.scroll_to_field(change.fieldname);
                                                }, index === 0? 0 : 1500);
                                            });
                                        
                                            frappe.show_alert({
                                                message: __("Successfully Applied " + request_type),
                                                indicator: "green"
                                            });

                                            frm.dirty();
                                            frm.disable_save();
                                            frm.page.set_primary_action(__("Apply Changes"), 
                                                function () {
                                                    displayApproveRequestDialog();
                                                }
                                            );
                                        }

                                        if (request_type == "Cancellation") {
                                            if (selected.cancel_today) {
                                                frm.events.cancel_subscription(frm, displayApproveRequestDialog);
                                            }
                                            else {
                                                frm.set_value("end_date", selected.cancellation_date);
                                                frm.set_value("cancel_at_period_end", 1);
                                                frm.refresh_field("end_date");
                                                frm.refresh_field("cancel_at_period_end");
                                                frm.scroll_to_field("end_date");
                                                frappe.show_alert({
                                                    message: __("Successfully Scheduled a Cancellation"),
                                                    indicator: "green"
                                                });
                                            }
                                        }

                                        if(request_type == "Resubscription") {
                                            if (selected.resubscribe_today) {
                                                frm.events.restart_subscription(frm, selected.resubscription_start_date, selected.resubscription_end_date, displayApproveRequestDialog);
                                            }
                                            else {
                                                frm.set_value("start_date", selected.resubscription_start_date);
                                                frm.refresh_field("start_date");
                                                frm.scroll_to_field("start_date");
                                                frappe.show_alert({
                                                    message: __("Successfully Scheduled a Renewal"),
                                                    indicator: "green"
                                                });
                                            }
                                        }
                                    }
                                );
                                update_request_select_dialog.show();
                            }
                        }
                    })
                },
                tools_button
            );
        }
    },

    toggle_email_queue_link: function (frm) {
        if (frm.doc.email_queue) {
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
    }
})

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

function displayIntro(frm, stripe_subscription_status, additional_info="") {
    frm.set_intro(__(
        `<div class="d-flex align-items-center" style="gap: 0.5rem;">
            ${stripe_logo}
            <b>Stripe Status: ${stripe_subscription_status}</b>${additional_info? " &bull; ": ""}<span>${additional_info}</span>
        </div>`
        
    ), stripe_subscription_status_color[stripe_subscription_status]);
}

function insertReloadButton(frm) {
    const reload_button = frm.add_custom_button("Reload Document", function() {
        frappe.dom.freeze("Reloading Document");

        frm.reload_doc().then(() => {
            frappe.dom.unfreeze();
        });
    });
    reload_button.attr("data-toggle", "tooltip")
                .attr("data-placement", "top")
                .attr("title", __("Reload Document"));
    reload_button.tooltip("dispose").tooltip();
    reload_button.html(`
        <svg class="es-icon es-line icon-sm" style="" aria-hidden="true">
            <use class="" href="#es-line-reload"></use>
        </svg>
    `);
}