// Copyright (c) 2025, VolksWagner and contributors
// For license information, please see license.txt

frappe.ui.form.on("Subscription Update Request", {
	refresh(frm) {
        if (frm.doc.status != "Requested") {
            frm.add_custom_button(__("Save and Notify Customer"), function() {
                frm.save();
            });
        }
        frm.events.toggle_reviewer_reqd(frm);
	},

    status: function (frm) {
        frm.events.toggle_reviewer_reqd(frm);
    },

    toggle_reviewer_reqd: function (frm) {
        frm.set_df_property(
            "reviewer", 
            "reqd", 
            frm.doc.status !== "Requested"
        )
    }
});

frappe.ui.form.on("Update Request Note", {
	description(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        row.status_when_written = frm.doc.status;
        frm.refresh_field("notes");
	},
});
