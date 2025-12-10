import datetime
import json
import frappe
import stripe
from decimal import Decimal
from frappe import _
from frappe.utils import fmt_money, get_url_to_form, today, now, split_emails
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from frappe.utils import now_datetime, add_to_date
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_bank_account_for_payment_entry
from erpusa.stripe_plus.api.webhook_receiver_subscription import receive_stripe_subscription_events

# stripe transaction fields
ST_FIELDS = [
    "stripe_transaction_id",
    "created",
    "object",
    "status",
    "description",
    "transaction_metadata",
    "destination",
    "livemode",
    "amount",
    "currency",
    "application",
    "application_fee",
    "application_fee_amount",
    "failure_balance_transaction",
    "failure_code",
    "failure_message",
    "paid",
    "refunded",
    "customer",
    "on_behalf_of",
    "invoice",
    "order",
    "payment_intent",
    "receipt_email",
    "receipt_url",
    "gross_amount",
    "captured",
    "amount_captured",
    "amount_refunded",
    "dispute",
    "disputed",
    "transfer_data",
    "transfer_group",
    "fraud_details",
    "advice_code",
    "network_advice_code",
    "network_decline_code",
    "network_status",
    "outcome_type",
    "risk_level",
    "reason",
    "seller_message",
    "payment_method",
    "payment_method_type",
    "payment_method_details",
    "card_status",
    "card_funding",
    "card_authorization_code",
    "card_network_transaction_id",
    "card_brand",
    "card_maximum_amount_capturable",
    "card_cvc_check",
    "source",
    "source_name",
    "source_funding",
    "source_metadata",
    "source_object",
    "source_customer",
    "source_fingerprint",
    "balance_transaction",
    "fee_details",
    "data_source",
]

# balance transaction fields
BT_FIELDS = [
    "bt_status",
    "bt_type",
    "bt_description",
    "bt_net",
    "bt_amount",
    "bt_fee",
]

# stripe payout fields
PO_FIELDS = [
    "stripe_payout_id",
    "created",
    "status",
    "description",
    "metadata",
    "destination",
    "livemode",
    "currency",
    "application",
    "application_fee",
    "application_fee_amount",
    "failure_balance_transaction",
    "failure_code",
    "failure_message",
    "type",
    "amount",
    "arrival_date",
    "automatic",
    "method",
    "statement_descriptor",
    "trace_id",
    "original_payout",
    "reconciliation_status",
    "reversed_by",
    "balance_transaction",
]

# payment completion estimate (for pending payment email)
METHOD_PROCESSING_DAYS = {
    "us_bank_account": "3-5",
    "sepa_debit": "5-7",
    "bacs_debit": "3"
}

@frappe.whitelist(allow_guest=True)
def receive_stripe_events():
    payload = frappe.request.get_data()
    sig_header = frappe.request.headers.get("Stripe-Signature")
    data = json.loads(payload)
    event_id = data.get("id")
    
    frappe.enqueue(
        "erpusa.stripe_plus.api.webhook_receiver.process_stripe_events",
        queue="short",
        job_name=event_id,
        enqueue_after_commit=False,
        payload=payload,
        sig_header=sig_header,
        data=data
    )
    
def process_stripe_events(payload, sig_header, data):
    validators = frappe.db.get_all("Stripe Plus Settings Webhook Validator", pluck="name")
    
    # verify if signing secret matches an entry in Stripe Plus Settings
    for validator in validators:
        stripe_settings_doc = frappe.get_doc("Stripe Plus Settings Webhook Validator", validator)
        secret = stripe_settings_doc.get_password("signing_secret")
        settings = frappe.get_doc("Stripe Settings", stripe_settings_doc.stripe_settings)
        api_key = settings.get_password("secret_key")

        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=secret
            )

            # store the id, data and attached object in the event
            id = data.get("id")
            type = data.get("type")
            data = data.get("data")["object"]

            # create or update a Stripe Log using the event details
            sl_doc_name =  frappe.db.exists("Stripe Log", {"event_id": data.get("id")})
            
            if not sl_doc_name:
                log_doc = frappe.new_doc("Stripe Log")
            else:
                log_doc = frappe.get_doc("Stripe Log", sl_doc_name)

            log_doc.datetime_received = now()
            log_doc.name = id
            log_doc.event_id = id
            log_doc.event_type = type
            log_doc.event_data = data

            try:
                log_doc.flags.ignore_permissions = True
                log_doc.save()
                
            except Exception as e:
                frappe.log_error(frappe.get_traceback(), _("Error Saving Stripe Log Document"))

            # create transaction doc
            if data.get("object") in ["charge", "payment_intent", "setup_intent", "refund"]:
                create_update_stripe_transaction(data, api_key, log_doc)
                
            # create payout doc
            elif data.get("object") == "payout":
                create_update_stripe_payout(data, log_doc, api_key)
            
            # process subscription-related events  
            elif data.get("object") in ["invoice", "customer", "subscription"]:
                receive_stripe_subscription_events(data)

            return "", 200
        
        except stripe.error.SignatureVerificationError:
            continue

def create_update_stripe_transaction(data, api_key, log_doc=None, remark=None, payout=None, return_mp_doc=False):
    # check if transaction is already recorded; return id if yes, otherwise create new doc
    st_doc_name = frappe.db.exists("Stripe Transaction", data.get("id"))

    if st_doc_name:
        doc = frappe.get_doc("Stripe Transaction", data.get("id"))

    else:
        doc = frappe.new_doc("Stripe Transaction")
        doc.stripe_transaction_id = data.get("id")
        
    # set common field values and metadata
    for field in ST_FIELDS:
        if field in data: 
            # if data is special—date or currency—perform additional validation
            if field == "currency":
                doc.set(field, data.get(field).upper())

            elif field == "created":
                doc.set(field, datetime.datetime.fromtimestamp(data.get(field)))

            elif "date" in field:
                doc.set(field, datetime.datetime.fromtimestamp(data.get(field)))

            elif "amount" in field and data.get(field):
                doc.set(field, data.get(field)/100)

            else:
                doc.set(field, data.get(field))
    doc.set("transaction_metadata", data.get("metadata"))

    # set values if data has outcome
    if data.get("outcome"):
        for key, value in data["outcome"].items():
            if key == "type":
                doc.set("outcome_type", value)

            else:
                doc.set(key, value)

    # set values if data has payment_method_details
    if data.get("payment_method_details"):
        pm_details = data.get("payment_method_details")

        doc.set("payment_method_type", pm_details.get("type"))

        if pm_details.get("type") == "card":
            for key, value in pm_details.get("card").items():
                doc.set("card_" + key, value)

            doc.set("card_cvc_check", pm_details.get("card")["checks"]["cvc_check"])
    
    # set values if data has source
    if data.get("source"):
        for key, value in data.get("source").items():
            if key == "id":
                doc.set("source", value)

            else:
                doc.set(key, value)

    # set values if data has balance transaction
    if data.get("balance_transaction"):
        balance_transaction = get_balance_transaction_details(data.get("balance_transaction"), api_key)

        for key, value in balance_transaction.items():
            if "bt_" + key in BT_FIELDS:
                if "bt_" + key in ["bt_net", "bt_amount", "bt_fee"]:
                    doc.set("bt_" + key, value/100)
                else:
                    doc.set("bt_" + key, value)

        if balance_transaction["fee_details"]:
            for fee_detail in balance_transaction["fee_details"]:
                if not frappe.db.exists("Stripe Fee Detail", {"parent": data.get('id'), "description": fee_detail["description"]}):
                    fee_detail_temp = fee_detail
                    fee_detail_temp["currency"] = fee_detail_temp["currency"].upper()
                    fee_detail_temp["amount"] = fee_detail_temp["amount"]/100
                    doc.append("fee_details", fee_detail_temp)
    
    # update history
    if log_doc:
        doc.append("data_source", {
            'stripe_log': log_doc.name,
            "status": log_doc.event_type,
            "datetime_received": log_doc.datetime_received
        })
    
    # link payout with transaction and add remarks for the update 
    if payout:
        doc.payout = payout
    if remark and doc.status != data.get("status"):
        doc.append("remarks", {
            "remark": remark
        })
    
    if doc.object == "charge":
    # get the recipient email and send a payment feedback to user
        metadata = doc.transaction_metadata
        payment_request_docname = frappe.db.exists("Payment Request", {"reference_name": metadata.get("docname"), "docstatus": ["!=", 2]})
        
        if doc.status in ["succeeded", "pending"] and \
        payment_request_docname and frappe.db.get_value("Payment Request", payment_request_docname, "email_to") and \
        frappe.db.exists("Stripe Transaction", data.get("id")) and \
        not (frappe.db.exists("Email Queue", {"reference_name": f"{doc.name}_{doc.status}"}) or frappe.db.exists("Email Queue", {"reference_name": f"{doc.name}"})):
            started_from_pending = frappe.db.count("Stripe Transaction Email Log", filters={"parent": doc.name, "status": "pending"}) and doc.status == "succeeded"
            
            frappe.sendmail(
                recipients=split_emails(frappe.db.get_value("Payment Request", payment_request_docname, "email_to")),
                subject=_("Your payment was successfully processed") if started_from_pending else _("Thank you for your payment"),
                message=frappe.render_template(
                    "erpusa/templates/html/payment_receipt.html",
                    {
                        "doctype": metadata.get("doctype"),
                        "docname": metadata.get("docname"),
                        "started_from_pending": started_from_pending,
                        "processing_days": METHOD_PROCESSING_DAYS.get(doc.payment_method_type),
                        "status": doc.status,
                        "receipt_url": data.get("receipt_url"),
                    },
                ),
                reference_doctype="Stripe Transaction",
                reference_name=f"{doc.name}_{doc.status}",
                now=True
            )

        # check if email was really sent and update email history
        email_log_name = frappe.db.exists("Email Queue", {"reference_name": f"{doc.name}_{doc.status}"})

        if email_log_name:
            doc_logged_emails = [email_log.email_reference for email_log in doc.email_log]

            if email_log_name not in doc_logged_emails:
                email_log_status = frappe.db.get_value("Email Queue", email_log_name, "status")
                email_log_datetime_date = None

                if email_log_status == "Sent":
                    email_log_datetime_date = frappe.db.get_value("Email Queue", email_log_name, "modified")

                doc.append("email_log", {
                    "email_reference": email_log_name,
                    "status": doc.status,
                    "datetime_sent": email_log_datetime_date
                })
        
        try:
            doc.flags.ignore_permissions = True
            doc.save()
            
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), _("Error Saving Stripe Transaction Document"))   

        # create a Merchant Payment doc
        mp_doc = create_update_merchant_payment(doc, metadata, api_key)

        # create a Sales Invoice doc
        if doc.status == "succeeded" and mp_doc and frappe.db.exists("Merchant Payment", mp_doc.name):
            if metadata and metadata.get('doctype') and metadata.get('docname'):
                if metadata.get('doctype') == "Sales Order":
                    create_sales_invoice(metadata.get('docname'), mp_doc)

                if doc.balance_transaction:
                # create a Payment Entry doc
                    create_payment_entry(mp_doc)

        if return_mp_doc:
            return mp_doc         

def create_update_stripe_payout(data, log_doc, api_key):
    # check if transaction is already recorded; return id if yes, otherwise create new doc
    if frappe.db.exists("Stripe Payout", data.get("id")):
        doc = frappe.get_doc("Stripe Payout", data.get("id"))
    else:
        doc = frappe.new_doc("Stripe Payout")
        doc.stripe_payout_id = data.get("id")
    
    # set common field values
    for field in PO_FIELDS:
        if field in data: 
            # if data is special—date or currency—perform additional validation
            if field == "currency":
                doc.set(field, data.get(field).upper())

            elif field == "created":
                doc.set(field, datetime.datetime.fromtimestamp(data.get(field)))

            elif "date" in field:
                doc.set(field, datetime.datetime.fromtimestamp(data.get(field)))

            elif field == "amount":
                doc.set(field, data.get(field)/100)

            else:
                doc.set(field, data.get(field))

    # set balance transaction values
    if data.get("balance_transaction"):
        balance_transaction = get_balance_transaction_details(data.get("balance_transaction"), api_key)

        for key, value in balance_transaction.items():
            if "bt_" + key in BT_FIELDS:
                if "bt_" + key in ["bt_net", "bt_amount", "bt_fee"]:
                    doc.set("bt_" + key, value/100)
                else:
                    doc.set("bt_" + key, value)

        if balance_transaction["fee_details"]:
            for fee_detail in balance_transaction["fee_details"]:
                if not frappe.db.exists("Stripe Fee Detail", {"parent": data.get('id'), "description": fee_detail["description"]}):
                    fee_detail_temp = fee_detail
                    fee_detail_temp["currency"] = fee_detail_temp["currency"].upper()
                    fee_detail_temp["amount"] = fee_detail_temp["amount"]/100
                    doc.append("fee_details", fee_detail_temp)
    
    # update history
    doc.append("data_source", {
        'stripe_log': log_doc.name,
        "status": log_doc.event_type,
        "datetime_received": log_doc.datetime_received
    })

    try:
        doc.flags.ignore_permissions = True
        doc.save()
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Error Saving Stripe Payout Document"))
    
    # update the charges and compute the involved in payout
    if doc.status == "paid":
        balance_transactions = stripe.BalanceTransaction.list(payout=doc.name, limit=100)
        sources = []
        charges = 0.0
        stripe_fees = 0.0
        refunds = 0.0
        adjustments = 0.0

        # update charges involved in payout
        for txn in balance_transactions.auto_paging_iter():
            if txn.type in ["charge", "payment"] and frappe.db.exists("Stripe Transaction", txn.source):
                charge_data = get_charge_details(txn.source, api_key)
                charge_remark = f'Updated {doc.created.strftime("%B %d, %Y")} through payout {doc.name}.'
                sources.append({
                    "source_id": txn.source,
                    "net_amount": txn.net,
                    "currency": txn.currency,
                    "fee_details": txn.fee_details,
                    "merchant_payment": frappe.db.exists("Merchant Payment", {"source": txn.source})
                })

                if charge_data:
                    create_update_stripe_transaction(charge_data, api_key, remark=charge_remark, payout=doc.name)
        
        # total the charges, stripe_fees, refunds and adjustments         
        for txn in balance_transactions.auto_paging_iter():
            if txn.type in ["charge", "payment"] and frappe.db.exists("Stripe Transaction", txn.source):
                charges = charges + txn.net
                
            if txn.type == "stripe_fee":
                stripe_fees = stripe_fees + txn.net
                
            if txn.type == "refund":
                refunds = refunds + txn.net
                
            if txn.type == "adjustment":
                adjustments = adjustments + txn.net
                
        total = charges + stripe_fees
        
        # refunds and adjustments are not handled at the moment, error message will be sent via email
        if refunds or adjustments or (Decimal(total) / Decimal('100') != Decimal(str(doc.amount))):
            notify_error_to_user(
                doc.name,
                charges/100,
                stripe_fees/100,
                refunds/100,
                adjustments/100,
                total/100,
                doc.amount,
                True if (refunds or adjustments) else False
            )
            
        else:
            # create journal entry
            je_doc = create_journal_entry(doc, sources, stripe_fees/100)
            
            if je_doc:
                doc.journal_entry = je_doc.name

            try:
                doc.flags.ignore_permissions = True
                doc.save()
                
            except Exception as e:
                frappe.log_error(frappe.get_traceback(), _("Error Saving Stripe Payout Document"))

def create_update_merchant_payment(stripe_transaction, metadata, api_key):
    mp_doc_name = frappe.db.exists("Merchant Payment", {"source": stripe_transaction.stripe_transaction_id})
    
    if not mp_doc_name:
        mp_doc = frappe.new_doc("Merchant Payment")

    else:
        mp_doc = frappe.get_doc("Merchant Payment", mp_doc_name)

    # set initial values -> for pending transactions
    mp_doc.merchant = "Stripe"
    mp_doc.source = stripe_transaction.stripe_transaction_id
    mp_doc.merchant_fee = 0.00
    mp_doc.gross_amount = 0.00
    mp_doc.net_amount = 0.00
    
    if metadata and metadata.get("doctype") and metadata.get("docname"):
        mp_doc.customer = frappe.db.get_value(metadata.get("doctype"), metadata.get("docname"), "customer")
        mp_doc.associated_payment_request = frappe.db.exists("Payment Request", {"reference_name": metadata.get("docname"), "docstatus": ["!=", 2]})

        if metadata.get("doctype") == "Sales Order":
            mp_doc.associated_sales_order = metadata.get("docname")

        if metadata.get("doctype") == "Sales Invoice":
            mp_doc.associated_sales_invoice = metadata.get("docname")
                
    # update fields if balance transaction is made
    balance_transaction = get_balance_transaction_details(stripe_transaction.balance_transaction, api_key)

    if balance_transaction:
        mp_doc.merchant_transaction_id = balance_transaction.get("id")
        mp_doc.merchant_fee = balance_transaction.get("fee") / 100
        mp_doc.gross_amount = balance_transaction.get("amount") / 100
        mp_doc.net_amount = balance_transaction.get("net") / 100
        mp_doc.stripe_status = balance_transaction.get("status").title()
        mp_doc.created = datetime.datetime.fromtimestamp(balance_transaction.get("created"))
        mp_doc.available_on = datetime.datetime.fromtimestamp(balance_transaction.get("available_on"))
        
    try:
        mp_doc.flags.ignore_permissions = True
        mp_doc.save()

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Error Saving Merchant Payment Document"))

    # notify user payment once merchnt payment doc is created
    if frappe.db.exists("Merchant Payment", mp_doc.name):
        frappe.enqueue(
        "erpusa.stripe_plus.api.webhook_receiver.notify_user",
            queue="short",
            merchant_payment=mp_doc
        )
            
    return mp_doc

def create_sales_invoice(sales_order, merchant_payment):
    # get the authorized user
    user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")

    # check if authorized user is set, do_not_create_invoice is disabled and if sales order was already paid
    if user_to_authorize and \
    not frappe.db.get_value("Payment Request", merchant_payment.associated_payment_request, "do_not_create_invoice") and \
    frappe.db.get_value("Sales Order", sales_order, "per_billed") == 0 :
            
        frappe.set_user(user_to_authorize)
        si_doc = make_sales_invoice(sales_order)
        si_meta = frappe.get_meta("Sales Invoice")
        update_stock_field = next((f for f in si_meta.fields if f.fieldname == "update_stock"), None)
        update_stock = 0

        if update_stock_field:
            update_stock = update_stock_field.default
            
        si_doc.update_stock = update_stock
        
        try:
            si_doc.flags.ignore_permissions = True
            si_doc.save()
            si_doc.submit()

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), _("Error Saving Sales Invoice Document"))
        
        # update Merchant Payment doc
        try:
            merchant_payment.associated_sales_invoice = si_doc.name
            merchant_payment.save()

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), _("Error Saving Merchant Payment Document"))

def create_payment_entry(merchant_payment):
    user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
    do_not_create_invoice = frappe.db.get_value("Payment Request", merchant_payment.associated_payment_request, "do_not_create_invoice")
    per_exists = frappe.db.exists(
        "Payment Entry Reference", 
        { "reference_name": merchant_payment.associated_sales_order if do_not_create_invoice else merchant_payment.associated_sales_invoice }
    )

    if user_to_authorize and not per_exists:
        frappe.set_user(user_to_authorize)

        # get the Payment Request doc and fetch the cost_center from settings
        pr_doc = frappe.get_doc("Payment Request", merchant_payment.associated_payment_request)
        cost_center = frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_cost_center")

        # reference the invoice instead of sales order if do_not_create_invoice is disabled
        if not do_not_create_invoice:
            pr_doc.reference_doctype = "Sales Invoice"
            pr_doc.reference_name = merchant_payment.associated_sales_invoice

            si_doc = frappe.get_doc("Sales Invoice", merchant_payment.associated_sales_invoice) # get the invoice
            si_items_with_cost_center = [item for item in si_doc.items if item.cost_center] # find the items in the invoice with cost center
            max_si_item = max(si_items_with_cost_center, key=lambda item: item.net_amount) if si_items_with_cost_center else None # find the highest amount in the list
            cost_center = max_si_item.cost_center if max_si_item.cost_center else frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_cost_center")

        pe_doc = pr_doc.create_payment_entry(submit=False)
        
        # sets the actual amount paid by the user
        for index, reference in enumerate(pe_doc.references):
            if reference.reference_name == pr_doc.reference_name:
                pe_doc.references[index].allocated_amount = merchant_payment.gross_amount
                
        pe_doc.mode_of_payment = frappe.get_value("Payment Request", merchant_payment.associated_payment_request, "mode_of_payment") 
        pe_doc.reference_no = frappe.get_value("Stripe Transaction", merchant_payment.source, "payment_intent")
        pe_doc.paid_amount = merchant_payment.net_amount

        # apply Merchant Payment as deduction
        pe_doc.append("deductions", {
            "account": frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_account"),
            "cost_center": cost_center,
            "amount": merchant_payment.merchant_fee,
            "description": merchant_payment.name,
        })
        
        # set the bank account
        if not pe_doc.bank_account and get_bank_account_for_payment_entry(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, as_dict=False):
            pe_doc.bank_account = get_bank_account_for_payment_entry(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, as_dict=False)

        try:
            pe_doc.save(ignore_permissions=True)

        except Exception as e:
            notify_error_to_user_merchant_payment(
                merchant_payment.name,
                _("The Payment Entry creation failed."),
                frappe.get_traceback()
            )
            frappe.log_error(frappe.get_traceback(), _("Error Saving Payment Entry Document"))
        
        # update Merchant Payment doc
        try:
            merchant_payment.associated_payment_entry = pe_doc.name
            merchant_payment.save()

        except Exception as e:
            notify_error_to_user_merchant_payment(
                merchant_payment.name,
                _("The Payment Entry association failed."),
                frappe.get_traceback()
            )
            frappe.log_error(frappe.get_traceback(), _("Error Saving Merchant Payment Document"))
            
        # submit Payment Entry doc according to settings
        if frappe.db.get_single_value("Stripe Plus Settings", "auto_submit_payment"):
            try:
                pe_doc.submit() 

            except Exception as e:
                frappe.log_error(frappe.get_traceback(), _("Error Submitting Payment Entry Document"))
             
def create_journal_entry(payout, sources=None, stripe_fees=None):
    user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")

    # create a new journal entry based on the Balance Transaction object
    if user_to_authorize and \
    not frappe.db.exists("Journal Entry", {"cheque_no": payout.name}) and \
    frappe.db.exists("Stripe Plus Settings Payout Account", {"payout_account": payout.destination}):
        frappe.set_user(user_to_authorize)

        # loop through the sources to create journal entry
        if sources:
            for index, source in enumerate(sources):
                if source.get('merchant_payment'):
                    # fetch the credit_account and credit_bank_account using Payment Request
                    credit_account = frappe.db.get_value(
                        "Payment Request",
                        frappe.db.get_value("Merchant Payment", source.get('merchant_payment'), "associated_payment_request"),
                        "payment_account"
                    )

                    credit_bank_account = frappe.db.get_value("Bank Account", {"account": credit_account}, "name")

            # fetch matching debit_account from settings; otherwise use default
            debit_accounts_name = frappe.db.exists("Stripe Plus Settings Payout Account", {"payout_account": payout.destination})

            if not debit_accounts_name:
                debit_accounts_name = frappe.db.exists("Stripe Plus Settings Payout Account", {"is_default_payout_account": True})

            je_doc = frappe.new_doc("Journal Entry")
            je_doc.entry_type = "Journal Entry"
            je_doc.posting_date = today()
            je_doc.cheque_no = payout.name
            je_doc.cheque_date = payout.created

            # add credit row if there are stripe fees
            if stripe_fees:
                stripe_fee_account = frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_account")
                stripe_fee_cost_center = frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_cost_center")

                je_doc.append("accounts", {
                    "account": stripe_fee_account,
                    "bank_account": get_bank_account_for_payment_entry("Receive", stripe_fee_account, stripe_fee_account, False, as_dict=False),
                    "debit_in_account_currency": abs(stripe_fees),
                    "cost_center": stripe_fee_cost_center
                })

            # fill credit row
            je_doc.append("accounts", {
                "account": credit_account,
                "bank_account": credit_bank_account,
                "credit_in_account_currency": abs(payout.amount) + abs(stripe_fees)
            })

            # fill debit row
            je_doc.append("accounts", {
                "account": frappe.db.get_value("Stripe Plus Settings Payout Account", debit_accounts_name, "erp_account"),
                "bank_account": frappe.db.get_value("Stripe Plus Settings Payout Account", debit_accounts_name, "erp_bank_account"),
                "debit_in_account_currency": abs(payout.amount)
            })
            
            try:
                je_doc.save()

            except Exception as e:
                frappe.log_error(frappe.get_traceback(), _("Error Saving Journal Entry Document"))

            # submit according to settings
            if frappe.db.get_single_value("Stripe Plus Settings", "auto_submit_journal"):
                try:
                    je_doc.submit() 

                except Exception as e:
                    frappe.log_error(frappe.get_traceback(), _("Error Submitting Journal Entry Document"))
    
            return je_doc

def get_charge_details(id, api_key):
    # get Charge object
    if id:
        stripe.api_key = api_key

        try:
            charge = stripe.Charge.retrieve(id)
            return charge
        
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), _("Error getting Charge Details"))
            return None

def get_balance_transaction_details(id, api_key):
    # get Balance Transaction object 
    if id:
        stripe.api_key = api_key

        try:
            balance_transaction = stripe.BalanceTransaction.retrieve(id)
            return balance_transaction
        
        except Exception as e:
            return {"Error getting Balance Transaction Details": str(e)}, 403

# send an error email to user if journal entry creation fails  
def notify_error_to_user(
        payout_id,
        charges,
        stripe_fees,
        refunds,
        adjustments,
        total,
        stripe_total,
        has_refunds_or_adjusments
    ):
    payout_url = get_url_to_form("Stripe Payout", payout_id)
    recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")
    message = frappe.render_template(
        "erpusa/templates/html/journal_entry_errors.html", {
            "payout_id": payout_id,
            "payout_url": payout_url,
            "charges": charges,
            "stripe_fees": stripe_fees,
            "refunds": refunds,
            "adjustments": adjustments,
            "total": total,
            "stripe_total": stripe_total,
            "has_refunds_or_adjustments": has_refunds_or_adjusments
        }
    )
    
    if recipients and not frappe.db.exists("Email Queue", {"reference_doctype": "Stripe Payout", "reference_name": payout_id}):
        frappe.sendmail(
            recipients=recipients.split(),
            subject=_("Stripe Payout Journal Entry failed"),
            message=message,
            reference_doctype="Stripe Payout",
            reference_name=payout_id,
            now=True
        )

def generate_realtime_notification_email_message(title, description, merchant_payment):
    return frappe.render_template(
        "erpusa/templates/html/realtime.html",
        {
            "title": title,
            "description": description,
            "id": merchant_payment.name,
            "merchant": merchant_payment.merchant,
            "merchant_transaction_id": merchant_payment.merchant_transaction_id,
            "customer": merchant_payment.customer,
            "gross_amount": fmt_money(merchant_payment.gross_amount)
        },
    )


def notify_error_to_user_merchant_payment(merchant_payment_name, summary, error_message):
    recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")

    if frappe.db.exists("Merchant Payment", merchant_payment_name):
        reference_name = merchant_payment_name + "_error_" + now()

        if recipients and not frappe.db.exists("Email Queue", {"reference_doctype": "Merchant Payment", "reference_name": reference_name}):
            message = frappe.render_template(
                "erpusa/templates/html/merchant_payment_errors.html",
                {
                    "merchant_payment": merchant_payment_name,
                    "summary": summary,
                    "error_message": error_message
                },
            )

            frappe.sendmail(
                recipients=recipients.split(),
                subject=_("Merchant Payment failed"),
                message=message,
                reference_doctype="Merchant Payment",
                reference_name=reference_name,
                now=True
            )


def notify_user(merchant_payment):
    # check if realtime notifications is enabled
    if frappe.db.get_single_value("Stripe Plus Settings", "turn_on_email_notifications") and frappe.db.get_single_value("Stripe Plus Settings", "notification_method") == "Realtime":
        recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")
        subject = _("Received {amount} from {customer}").format(amount=fmt_money(merchant_payment.gross_amount, customer=merchant_payment.customer))
        reference_name = None

        if merchant_payment.source:
            reference_name = merchant_payment.source + "_notification"
        
        if not (frappe.db.exists("Email Queue", {"reference_name": merchant_payment.source + "_notification"}) or frappe.db.exists("Email Queue", {"reference_name": merchant_payment.source})):
            frappe.sendmail(
                recipients=recipients.split(),
                subject=subject,
                message=generate_realtime_notification_email_message(
                    title=_("{customer} sent {amount}").format(customer=merchant_payment.customer, amount=fmt_money(merchant_payment.gross_amount)),
                    description=_("More information about this payment is shown below."),
                    merchant_payment=merchant_payment
                ),
                reference_doctype="Stripe Transaction",
                reference_name=reference_name,
                now=True
            )