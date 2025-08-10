const stripe_subscription_status_color = {
    'Incomplete': 'yellow',
    'Incomplete Expired': 'yellow',
    'Trialing': 'green',
    'Active': 'green',
    'Past Due': 'red',
    'Canceled': 'orange',
    'Unpaid': 'red',
    'Paused': 'yellow'
}

frappe.ui.form.on("Subscription", {
    refresh: function(frm) {
        if (frm.doc.stripe_subscription_id) {
            frm.set_intro(__(
                `<div class="d-flex align-items-center" style="gap: 0.5rem;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-stripe" viewBox="0 0 16 16">
                        <path d="M2 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2zm6.226 5.385c-.584 0-.937.164-.937.593 0 .468.607.674 1.36.93 1.228.415 2.844.963 2.851 2.993C11.5 11.868 9.924 13 7.63 13a7.7 7.7 0 0 1-3.009-.626V9.758c.926.506 2.095.88 3.01.88.617 0 1.058-.165 1.058-.671 0-.518-.658-.755-1.453-1.041C6.026 8.49 4.5 7.94 4.5 6.11 4.5 4.165 5.988 3 8.226 3a7.3 7.3 0 0 1 2.734.505v2.583c-.838-.45-1.896-.703-2.734-.703"></path>
                    </svg>
                    <b>Stripe Status: ${frm.doc.stripe_subscription_status}</b>
                </div>`
                
            ), stripe_subscription_status_color[frm.doc.stripe_subscription_status]);
            frm.set_df_property("autocharge_with_stripe", "read_only", true)
            frm.set_df_property("payment_gateway_account", "read_only", true)
            frm.set_df_property("payment_method_configuration", "read_only", true)
        }
    }
})