// This is your test secret API key.
frappe.ready(function() {
  const stripe = Stripe("{{ publishable_key }}");

  initialize();

  // Create a Checkout Session
  async function initialize() {
    const fetchClientSecret = async () => {
      const response = await fetch("/api/method/erpusa.templates.pages.stripe_plus_subs_checkout.create_checkout_session", {
        method: "POST",
        headers: { 
            "Content-Type": "application/json",
            "X-Frappe-CSRF-Token": frappe.csrf_token
        },
        body: JSON.stringify({ 
          "subscription": "{{ subscription }}",
          "customer": "{{ customer }}",
          "gateway_controller": "{{ gateway_controller }}",
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