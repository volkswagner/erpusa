frappe.ui.form.on("Subscription Plan", {
    refresh: function(frm) {
        if (frm.doc.stripe_price_id) {
            const locked_fields = ["currency", "item", "price_determination", "price_list", "cost", "billing_interval", "billing_interval_count"];

            locked_fields.forEach(function(field) {
                frm.set_df_property(field, "read_only", 1);
            });

            frm.set_intro(__("This Subscription Plan is linked to an active Stripe-enabled Subscription. Some fields are locked and cannot be edited."), "yellow")
        }
    }
})