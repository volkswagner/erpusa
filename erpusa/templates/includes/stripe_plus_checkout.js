frappe.ready(function() {
  const stripe = Stripe("{{ publishable_key }}");
  
  initialize();
    async function initialize() {
    const fetchClientSecret = async () => {
      const response = await fetch("/api/method/erpusa.templates.pages.stripe_plus_checkout.create_fetch_checkout_session", {
        method: "POST",
        headers: { 
            "Content-Type": "application/json",
            "X-Frappe-CSRF-Token": frappe.csrf_token
        },
        body: JSON.stringify({ 
          "pm_configuration": "{{ pm_configuration }}"=="None"? null : "{{ pm_configuration }}",
          "doctype": "{{ to_pay_doctype }}",
          "docname": "{{ to_pay_id }}",
          "gateway_controller": "{{ gateway_controller }}",
          "request_name": "{{ reference_docname }}"
        })
      });
      const { message: { clientSecret, redirect } } = await response.json();
      return clientSecret;
    };

    const checkout = await stripe.initEmbeddedCheckout({
      fetchClientSecret,
    });

    // Mount Checkout
    checkout.mount('#checkout');
  }
})