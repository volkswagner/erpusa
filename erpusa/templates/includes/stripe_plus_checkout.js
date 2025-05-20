// This is your test publishable API key.

frappe.ready(function() {
  const accentColor = "rgb(103, 93, 255)";
  const stripe = Stripe("{{ publishable_key }}");
  
  let elements;
  
  initialize();
  document
    .querySelector("#payment-form")
    .addEventListener("submit", handleSubmit);
  
  function isValidEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
  }

  function showInvalidEmailMessage(email_address) {
    if (!isValidEmail(email_address)) {
      document.getElementById("email-help-box").innerHTML = `
        <div class="alert alert-danger py-1 px-2 m-1 d-flex align-items-center" style="gap: 0.5rem">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" style="display: inline-block; vertical-align: text-bottom;"><path d="M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0 1 14.082 15H1.918a1.75 1.75 0 0 1-1.543-2.575Zm1.763.707a.25.25 0 0 0-.44 0L1.698 13.132a.25.25 0 0 0 .22.368h12.164a.25.25 0 0 0 .22-.368Zm.53 3.996v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"></path></svg>
            <small>Invalid email address. Payment may not proceed.</small>
        </div>
      `
    }
    else
    {
      document.getElementById("email-help-box").innerHTML = ""
    }
  }

  let receipt_email_node = document.getElementById("receipt-email")
  showInvalidEmailMessage(receipt_email_node.value)
  receipt_email_node.addEventListener("change", function(event) {
    showInvalidEmailMessage(event.target.value)
  })

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
        return_url: "{{ frappe.utils.get_url() }}/stripe_plus_return?reference_docname={{ reference_docname }}&gateway_controller={{ gateway_controller }}&to_pay_id={{ to_pay_id }}&amount={{ amount }}",
        payment_method_data: {
          billing_details: {
            email: receipt_email_node.value, 
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