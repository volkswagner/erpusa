frappe.ready(function() {
	const is_new = Boolean("{{ data.is_new }}")
	console.log("{{ data.subscription }}")
	console.log("{{ data.customer }}")

	if (is_new) {
		// frappe.web_form.set_value("subscription", "{{ data.subscription }}");
		// frappe.web_form.set_value("request_details", "{{ data.subscription }}");
	}
})