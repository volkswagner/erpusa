frappe.ready(function() {
    if ("{{ session_status }}" === 'open') {
      window.location.replace("{{ payment_url }}")
    }
})