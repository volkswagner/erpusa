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

frappe.ui.form.on("Subscription", {
    setup: function (frm) {
        frm.set_query("user_account_representative", function (doc) {
			return {
				query: "erpnext.selling.doctype.customer.customer.get_customer_primary_contact",
				filters: {
					customer: doc.party,
				},
			};
		});
    },

    refresh: function(frm) {
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
                        let additional_info = r.message.status == "Sent"? "Customer has been notified to set up a payment method." : "An email is scheduled to be sent to the customer at the start of the subscription.";
                        displayIntro(frm, "Email " + r.message.status, additional_info);
                    }
                });
            }
        }

        if (frm.doc.stripe_subscription_id) {
            ["autocharge_with_stripe","payment_gateway_account", "payment_method_configuration"].forEach(function(field) {
                frm.set_df_property(field, "read_only", true);
            })

        }
        
        frm.events.toggle_locked_fields(frm);
        frm.events.toggle_stripe_plus_fields_read_only(frm);
        insertReloadButton(frm);
    },

    autocharge_with_stripe: function(frm) {
        frm.events.set_user_account_representative(frm);
        frm.events.toggle_locked_fields(frm);
        frm.events.toggle_stripe_plus_fields_read_only(frm);
    },

    party_type: function (frm) {
        if (frm.doc.party_type !== "Customer") {
            frm.set_value("autocharge_with_stripe", 0);
        }
    },

    party: function (frm) {
        frm.events.set_user_account_representative(frm);
    },

    set_user_account_representative: function (frm) {
        if (frm.doc.autocharge_with_stripe && frm.doc.party) {
            frappe.call({
                method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.get_customer_contact",
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

    toggle_locked_fields: function (frm) {
        if (frm.doc.autocharge_with_stripe) {
            const locked_fields = ["generate_invoice_at", "generate_new_invoices_past_due_date", "submit_invoice"];
            const locked_message = `
                <div class="alert alert-warning p-2 mt-2" role="alert">
                        <small>Field is locked to allow autocharging with Stripe.</small>
                </div>`;

            frm.set_value("generate_new_invoices_past_due_date", 1);
            frm.set_value("submit_invoice", 1);
            frm.set_value("generate_invoice_at", "Beginning of the current subscription period");

            locked_fields.forEach(function(field) {
                frm.set_df_property(field, "read_only", 1);
                frm.set_df_property(
                    field,
                    "description",
                    locked_message
                );
            });
        }

        else {
            frm.set_df_property("generate_invoice_at", "read_only", 0);
            frm.set_df_property("generate_invoice_at", "description", null);
        }
    },

    toggle_stripe_plus_fields_read_only: function (frm) {
        frm.set_df_property("payment_gateway_account", "reqd", frm.doc.autocharge_with_stripe);
        frm.set_df_property("user_account_representative", "reqd", frm.doc.autocharge_with_stripe);
    },

    cancel_subscription: function (frm) {
		frappe.confirm(
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
                            cancel_subscription_dialog.hide();
                        }
                    }
                });
			},
		);
	},
})

function displayIntro(frm, stripe_subscription_status, additional_info="") {
    frm.set_intro(__(
        `<div class="d-flex align-items-center" style="gap: 0.5rem;">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-stripe" viewBox="0 0 16 16">
                <path d="M2 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2zm6.226 5.385c-.584 0-.937.164-.937.593 0 .468.607.674 1.36.93 1.228.415 2.844.963 2.851 2.993C11.5 11.868 9.924 13 7.63 13a7.7 7.7 0 0 1-3.009-.626V9.758c.926.506 2.095.88 3.01.88.617 0 1.058-.165 1.058-.671 0-.518-.658-.755-1.453-1.041C6.026 8.49 4.5 7.94 4.5 6.11 4.5 4.165 5.988 3 8.226 3a7.3 7.3 0 0 1 2.734.505v2.583c-.838-.45-1.896-.703-2.734-.703"></path>
            </svg>
            <b>Stripe Status: ${stripe_subscription_status}</b>${additional_info? " &bull; ": ""}<span>${additional_info}</span>
        </div>`
        
    ), stripe_subscription_status_color[stripe_subscription_status]);
}

function insertReloadButton(frm) {
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
}