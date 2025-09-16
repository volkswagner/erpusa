frappe.ready(function() {
	const is_new = Boolean("{{ data.is_new }}")

	if (is_new) {
		frappe.web_form.set_value("subscription", "{{ data.subscription }}");
		frappe.web_form.set_value("customer", "{{ customer }}");
		frappe.call({
			method: "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.calculate_subscription_plan_total",
			args: {
				subscription: "{{ data.subscription }}",
				is_doc: false,
				include_billing: false,
				include_grand_total: false
			},
			callback: function (r) {
				if (r.message) {
					let plans = r.message
					let field = frappe.web_form.get_field("plans");

                    plans.forEach((plan, index) => {
                        field.grid.add_new_row();

                        let grid_rows = field.grid.grid_rows;
                        let last_row = grid_rows[grid_rows.length - 1];

                        last_row.doc.plan = plan.plan;
                        last_row.doc.price = plan.price;
                        last_row.doc.qty = plan.qty;
                        last_row.doc.amount = plan.amount;
                        last_row.doc.new_qty = plan.qty;
                        last_row.doc.new_amount = plan.amount;

                        last_row.refresh();
                    });
				}
			}
		});

		const grid = frappe.web_form.fields_dict["plans"].grid;
		grid.wrapper.on('change', 'input, select, textarea', function() {
			const $new_qty_container = $(this).closest('.grid-static-col');
			const $new_amount_input = $new_qty_container.next('.grid-static-col').find('input');
			const $price_input = $new_qty_container.siblings('.grid-static-col[data-fieldname="price"]').find('input');

			if ($new_amount_input.length) {
				$new_amount_input.val(
					parseFloat($(this).val()) * parseFloat($price_input.val())
				);
				$new_amount_input.trigger('change');
			}
		});

		frappe.web_form.on("change_end_date", function() {
			frappe.web_form.set_df_property(
				"new_end_date",
				"reqd",
				frappe.web_form.get_value("change_end_date")
			);
		});
	}
})