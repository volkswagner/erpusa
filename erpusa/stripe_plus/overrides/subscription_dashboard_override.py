import frappe

def get_dashboard_data(data):
   return {
      "fieldname": "subscription",
      "non_standard_fieldnames": {
         "Payment Entry": "reference_name",
      },
      "internal_links": {
         "Payment Entry": ["references", "reference_name"],
      }, 
      "internal_links": {}, 
      "transactions": [
         {
            "label": "Buying", 
            "items": ["Purchase Invoice"]
         }, 
         {
            "label": "Selling", 
            "items": ["Sales Invoice", "Payment Entry"]
         }
      ], 
   }