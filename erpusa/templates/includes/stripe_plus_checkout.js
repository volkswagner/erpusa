// This is your test publishable API key.

frappe.ready(function() {
  const accentColor = "rgb(103, 93, 255)";
  const stripe = Stripe("{{ publishable_key }}");
  
  let elements;
  
  initialize();
  document
    .querySelector("#payment-form")
    .addEventListener("submit", handleSubmit);
  
  
  // Fetches a payment intent and captures the client secret
  async function initialize() {
    const response = await fetch("/api/method/erpusa.templates.pages.stripe_plus_checkout.create_fetch_payment_intent", {
      method: "POST",
      headers: { 
          "Content-Type": "application/json",
          "X-Frappe-CSRF-Token": frappe.csrf_token
          // "X-Frappe-CSRF-Token": csrfToken
      },
      body: JSON.stringify({ 
        "amount": "{{ amount_int }}", 
        "pm_configuration": "{{ pm_configuration }}"=="None"? null : "{{ pm_configuration }}",
        "doctype": "{{ to_pay_doctype }}",
        "docname": "{{ to_pay_id }}",
        "gateway_controller": "{{ gateway_controller }}",
        "request_name": "{{ reference_docname }}"
    })
    });
    const { message: { clientSecret, redirect } } = await response.json();

    if (redirect) {
        window.location.href = redirect;
    }
  
    const appearance = {
      theme: 'flat',
      variables: {
        iconColor: "accentColor",
        fontLineHeight: '1.5',
        borderRadius: '10px',
        colorBackground: 'rgb(243, 243, 243)',
        accessibleColorOnColorPrimary: '#262626',
        tabIconHoverColor: 'white',
        tabIconSelectedColor: 'white'
      },
      rules: {
        '.Block': {
          backgroundColor: 'var(--colorBackground)',
          boxShadow: 'none',
          padding: '12px'
        },
        '.Input:focus': {
          backgroundColor: 'white',
        },
        '.Input': {
          padding: '12px'
        },
        '.Input:disabled, .Input--invalid:disabled': {
          color: 'lightgray'
        },
        '.Tab': {
          padding: '10px 12px 8px 12px',
          border: 'none'
        },
        '.Tab:hover': {
          border: 'none',
          backgroundColor: accentColor,
          boxShadow: '0',
          color: 'white'
        },
        '.TabIcon': {
          fill: accentColor
        },
        '.TabIcon--selected': {
          fill: 'white'
        },
        '.Tab--selected, .Tab--selected:focus, .Tab--selected:hover': {
          border: 'none',
          backgroundColor: accentColor,
          color: "white",
          boxShadow: 'none'
        },
        '.Label': {
          fontWeight: '500'
        },
        '.Submit': {
        content: 'Complete Payment'
      }
      }
    };
    elements = stripe.elements({ appearance, clientSecret })
  
    const paymentElementOptions = {
      layout: 'tabs',
      // defaultPaymentMethodType: 'bank_transfer',
      paymentMethodOrder: ['us_bank_account', 'card']
    };
  
    const paymentElement = elements.create("payment", paymentElementOptions);
    paymentElement.mount("#payment-element");
  }
  
  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
  
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        // Make sure to change this to your payment completion page
        return_url: "https://emower.hvgeek.com/stripe_plus_return?reference_docname={{ reference_docname }}&gateway_controller={{ gateway_controller }}&to_pay_id={{ to_pay_id }}&amount={{ amount }}",
        payment_method_data: {
          billing_details: {
            email: `${document.getElementById("receipt-email").value}`, 
          }
        }
      },
    });
  
    // This point will only be reached if there is an immediate error when
    // confirming the payment. Otherwise, your customer will be redirected to
    // your `return_url`. For some payment methods like iDEAL, your customer will
    // be redirected to an intermediate site first to authorize the payment, then
    // redirected to the `return_url`.
    if (error.type === "card_error" || error.type === "validation_error") {
      showMessage(error.message);
    } else {
      showMessage("An unexpected error occurred.");
    }
  
    setLoading(false);
  }
  
  // ------- UI helpers -------
  
  function showMessage(messageText) {
    const messageContainer = document.querySelector("#payment-message");
  
    messageContainer.classList.remove("hidden");
    messageContainer.textContent = messageText;
  
    setTimeout(function () {
      messageContainer.classList.add("hidden");
      messageContainer.textContent = "";
    }, 4000);
  }
  
  // Show a spinner on payment submission
  function setLoading(isLoading) {
    if (isLoading) {
      // Disable the button and show a spinner
      document.querySelector("#submit").disabled = true;
      document.querySelector("#spinner").classList.remove("hidden");
      document.querySelector("#button-text").classList.add("hidden");
    } else {
      document.querySelector("#submit").disabled = false;
      document.querySelector("#spinner").classList.add("hidden");
      document.querySelector("#button-text").classList.remove("hidden");
    }
  }
})