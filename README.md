## erpUSA
An extension of ERPNext with goodies for users in the USA.

IMPORTANT: This app is under heavy development and should be considered BETA software at this time. Please use in a test/dev environment. If you encounter any issues, please raise them via the issues tab in this Repository.

#### Main Modules
1. ERP USA
2. Stripe Plus
   - Customizable checkout/payment experience for customers through Stripe’s payment configuration feature
   - Automation in notifications, invoicing and payment collection

#### Key Features
1. ERP USA
2. Stripe Plus
     - Make a different combination of payment methods (called payment configuration) in requesting payment from a customer.
     - Assign a payment configuration to a customer so that every time they have to pay, there’s no need to manually change the payment configuration.
     - Get real time or digest notifications when a customer pays.
     - Have your Sales Invoice, Payment Entry and Journal Entry created for you without any intervention.

#### Minor Enhancements
1. Customized Payment Entry form (moved check reference info towards the top of form).
2. Added script to automatically assign associated bank account via account/payment method.
---
### Installation
ERP USA requires the following apps and libraries:
- ERPNext app (https://github.com/frappe/erpnext)
- Payments app (https://github.com/frappe/payments)
- Stripe library (https://github.com/stripe/stripe-python)

After installing the dependencies, run the following commands:
1. Install Stripe Plus only or the whole erpUSA:
    - ```bench get-app --branch stripe-plus https://github.com/volkswagner/erpusa```
    - ```bench get-app https://github.com/volkswagner/erpusa```
2. ```bench --site {your_site} install-app erpusa```
3. ```bench --site {your_site} migrate```
