frappe.listview_settings["Sales Invoice"] = {
    onload: function(listview) {
        listview.page.add_action_item(__("Delivery Note"), () => {
			erpnext.bulk_transaction_processing.create(listview, "Sales Invoice", "Delivery Note");
		});

		listview.page.add_action_item(__("Payment"), () => {
			erpnext.bulk_transaction_processing.create(listview, "Sales Invoice", "Payment Entry");
		});
        listview.page.add_actions_menu_item("Single Payment", () => {
            let selected = listview.get_checked_items();
            selected.forEach(function(selected_item) {
                if (selected_item.docstatus !== 1) {
                    frappe.throw(__("Can only create invoices for submitted invoices."));
                }
            })

            let prompt = frappe.prompt([
                {
                    fieldname: "message",
                    fieldtype: "HTML",
                    options: `
                        To create a single Payment Entry for the <b>${selected.length}</b> invoices, enter the reference details.
                        <br/><br/>
                    `
                },
                {
                    label: "Paid Amount",
                    fieldname: "paid_amount",
                    fieldtype: "Currency",
                    min: 0,
                    reqd: 1,
                },
                {
                    label: "Reference No.",
                    fieldname: "reference_no",
                    fieldtype: "Data",
                    reqd: 1,
                },
                {
                    label: "Reference Date",
                    fieldname: "reference_date",
                    fieldtype: "Datetime",
                    reqd: 1,
                },
            ], () => {});

            prompt.set_title("Create Payment Entry");

            prompt.set_primary_action("Continue", function (values) {
                frappe.call({
                    method: "erpusa.erpusa_accounts.utils.sales_invoice.create_bulk_payment_entry",
                    freeze: true,
                    freeze_message: __("Creating Payment Entry"),
                    args: {
                        invoices: selected,
                        paid_amount: values.paid_amount,
                        reference_no: values.reference_no,
                        reference_date: values.reference_date
                    },
                    callback: function (r) {
                        frappe.set_route("Form", "Payment Entry", r.message);
                    }
                });
            });
        });
    }
};