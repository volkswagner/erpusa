import frappe
from frappe import _
import json
import stripe
from datetime import datetime
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

ST_FIELDS = [
    "stripe_transaction_id",
    "created",
    "object",
    "status",
    "description",
    "transaction_metadata",
    "destination",
    "livemode",
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

BT_FIELDS = [
    "bt_status",
    "bt_type",
    "bt_description",
    "bt_net",
    "bt_amount",
    "bt_fee",
]

@frappe.whitelist(allow_guest=True)
def receive_stripe_events():
    payload = frappe.request.get_data()
    validators = frappe.db.get_all("Stripe Plus Settings Webhook Validator", pluck="name")
    sig_header = frappe.request.headers.get("Stripe-Signature")
    
    for validator in validators:
        doc = frappe.get_doc("Stripe Plus Settings Webhook Validator", validator)
        secret = doc.get_password("signing_secret")
        settings = frappe.get_doc("Stripe Settings", doc.stripe_settings)
        api_key = settings.get_password("secret_key")
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=secret
            )

            data = json.loads(payload)

            id = data.get("id") # get event id
            type = data.get("type")  # get type of event
            data = data.get("data")["object"] # get request details
            
            log_doc = frappe.new_doc("Stripe Log")
            log_doc.datetime_received = frappe.utils.now()
            log_doc.name = id
            log_doc.event_id = id
            log_doc.event_type = type
            log_doc.event_data = data
            log_doc.save(ignore_permissions=True)

            stripe_transaction = create_update_stripe_transaction(data, log_doc, api_key)

            # if "payout.paid" in log_doc.event_type:
            #     create_payment_entry(id, log_doc.datetime_received)
            
            return "", 200
        except stripe.error.SignatureVerificationError:
            continue

def create_update_stripe_transaction(data, log_doc, api_key):
    if frappe.db.exists("Stripe Transaction", data.get("id")):
        doc = frappe.get_doc("Stripe Transaction", data.get("id"))
    else:
        doc = frappe.new_doc("Stripe Transaction")
        doc.stripe_transaction_id = data.get("id")
    
    for field in ST_FIELDS:
        if field in data:
            if field == "currency":
                doc.set(field, data[field].upper())
            elif field == "created":
                doc.set(field, datetime.fromtimestamp(data[field]))
            elif "date" in field:
                doc.set(field, datetime.fromtimestamp(data[field]))
            else:
                doc.set(field, data[field])

    doc.set("transaction_metadata", data.get("metadata"))

    if data.get("outcome"):
        for key, value in data["outcome"].items():
            if key == "type":
                doc.set("outcome_type", value)
            else:
                doc.set(key, value)

    if data.get("payment_method_details"):
        doc.set("payment_method_type", data["payment_method_details"]["type"])
        if data["payment_method_details"]["type"] == "card":
            for key, value in data["payment_method_details"]["card"].items():
                doc.set("card_" + key, value)
            doc.set("card_cvc_check", data["payment_method_details"]["card"]["checks"]["cvc_check"])

    if data.get("source"):
        for key, value in data["source"].items():
            if key == "id":
                doc.set("source", value)
            else:
                doc.set(key, value)

    if data.get("balance_transaction"):
        balance_transaction = get_balance_transaction_details(data["balance_transaction"], api_key)

        for key, value in balance_transaction.items():
            if "bt_" + key in BT_FIELDS:
                doc.set("bt_" + key, value)

        if balance_transaction["fee_details"]:
            for fee_detail in balance_transaction["fee_details"]:
                fee_detail_temp = fee_detail
                fee_detail_temp["currency"] = fee_detail_temp["currency"].upper()
                doc.append("fee_details", fee_detail_temp)
    
    doc.append("data_source", {
        'stripe_log': log_doc.name,
        "status": log_doc.event_type,
        "datetime_received": log_doc.datetime_received
    })

    try:
        doc.flags.ignore_permissions = True
        doc.save()
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _('Error Saving Document'))

    if doc.object == "charge":
        mp_doc = create_update_merchant_payment(doc, api_key)
        if doc.status == "succeeded" and mp_doc:
            create_payment_entry(mp_doc)
    
    # if doc.object == "payout":

    
    return doc.name

def get_balance_transaction_details(id, api_key):
    if id:
        stripe.api_key = api_key
        try:
            balance_transaction = stripe.BalanceTransaction.retrieve(id)
            return balance_transaction
        except Exception as e:
            return {"error": str(e)}, 403

def create_update_merchant_payment(stripe_transaction, api_key):
    balance_transaction = get_balance_transaction_details(stripe_transaction.balance_transaction, api_key)
    if balance_transaction:
        metadata = stripe_transaction.transaction_metadata
        mp_doc_name = frappe.db.exists("Merchant Payment", {"source": stripe_transaction.stripe_transaction_id})
        
        if not mp_doc_name:
            mp_doc = frappe.new_doc("Merchant Payment")
        else:
            mp_doc = frappe.get_doc("Merchant Payment", mp_doc_name)

        mp_doc.merchant = "Stripe"
        mp_doc.merchant_transaction_id = balance_transaction.get("id")
        mp_doc.source = stripe_transaction.stripe_transaction_id
        mp_doc.merchant_fee = balance_transaction.get("fee") / 100
        mp_doc.gross_amount = balance_transaction.get("amount") / 100
        mp_doc.net_amount = balance_transaction.get("net") / 100
        mp_doc.status = balance_transaction.get("status").title()
        mp_doc.created = datetime.fromtimestamp(balance_transaction.get("created"))
        mp_doc.available_on = datetime.fromtimestamp(balance_transaction.get("available_on"))
        
        if metadata and metadata.get("doctype") and metadata.get("docname"):
            mp_doc.customer = frappe.db.get_value(metadata.get("doctype"), metadata.get("docname"), "customer")
            if metadata.get("doctype") == "Sales Order":
                mp_doc.associated_sales_order = metadata.get("docname")
            if metadata.get("doctype") == "Sales Invoice":
                mp_doc.associated_sales_invoice = metadata.get("docname")

        try:
            mp_doc.flags.ignore_permissions = True
            mp_doc.save()
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), _('Error Saving Document'))
            
        return mp_doc

    else:
        return None

def create_payment_entry(merchant_payment):
    frappe.set_user("Administrator")
    if merchant_payment.associated_sales_order:
        per_exists = frappe.db.exists("Payment Entry Reference", merchant_payment.associated_sales_order)
        doctype = "Sales Order"
        docname = merchant_payment.associated_sales_order
    else:
        per_exists = frappe.db.exists("Payment Entry Reference", merchant_payment.associated_sales_invoice)
        doctype = "Sales Invoice"
        docname = merchant_payment.associated_sales_invoice
    
    if not per_exists and doctype and docname:
        pe_doc = get_payment_entry(
            dt=doctype,
            dn=docname,
            # bank_account="Marky Mark Stripe - Stripe",
            reference_date=merchant_payment.created,
            ignore_permissions=True,
            created_from_payment_request=True,
        )
        
        pe_doc.reference_no = frappe.get_value("Stripe Transaction", merchant_payment.source, "payment_intent")
        pe_doc.append("deductions", {
            "reference_doctype": "Merchant Payment",
            "reference_name": merchant_payment.name,
            "allocated_amount": merchant_payment.merchant_fee,
            "outstanding_amount": merchant_payment.merchant_fee,
            "total_amount": merchant_payment.merchant_fee
        })

        try:
            pe_doc.flags.ignore_permissions = True
            pe_doc.save()
            merchant_payment.status = "Paid"
            merchant_payment.save()
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), _('Error Saving Document'))

def create_journal_entry(payout_id):
    balance_transactions = stripe.BalanceTransaction.list(payout=payout_id, limit=100)
    sources = []

    # store the sources of the payout
    for txn in balance_transactions.auto_paging_iter():
        # add the source if the transaction was accounted for
        if frappe.db.exists("Stripe Transaction", txn.source):
            sources.append({
                "source_id": txn.source,
                "net_amount": txn.net,
                "currency": txn.currency,
                "fee_details": txn.fee_details
            })

    # loop through the sources to create payment entry
    for index, source in enumerate(sources):
        pass
	
	
