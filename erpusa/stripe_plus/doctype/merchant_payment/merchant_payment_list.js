frappe.listview_settings["Merchant Payment"] = {
    // Force Frappe to fetch the field for every list row
    add_fields: ["payment_status"],

    get_indicator(doc) {
        if (doc.payment_status === "succeeded") {
            return [__("Succeeded"), "green", "payment_status,=,succeeded"];
        }
        else if (doc.payment_status === "failed") {
            return [__("Failed"), "red", "payment_status,=,failed"];
        }

        return [__("Pending"), "blue", "payment_status,=,pending"];
    }
};