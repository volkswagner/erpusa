import frappe
from frappe import _
import urllib.parse
import stripe
import datetime
import json
import re
from frappe.utils import format_timedelta, format_time
from frappe.email.doctype.auto_email_report.auto_email_report import make_links, update_field_types
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings import get_bank_account
from frappe.utils import (
	format_time,
	get_url_to_report,
	global_date_format,
	now,
    fmt_money
)
from erpusa.stripe_plus.hook.daily_task import find_schedule_date_ranges

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

BT_FIELDS = [
    "bt_status",
    "bt_type",
    "bt_description",
    "bt_net",
    "bt_amount",
    "bt_fee",
]

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

            if "charge" in type:
                create_update_stripe_transaction(data, log_doc, api_key)
            elif "payout" in type:
                create_update_stripe_payout(data, log_doc, api_key)
            return "", 200
        except stripe.error.SignatureVerificationError:
            continue

def create_update_stripe_transaction(data, log_doc, api_key):
    # check if transaction is already recorded; return id if yes, otherwise create new doc
    st_doc_name = frappe.db.exists("Stripe Transaction", data.get("id"))
    if st_doc_name:
        doc = frappe.get_doc("Stripe Transaction", data.get("id"))
    else:
        doc = frappe.new_doc("Stripe Transaction")
        doc.stripe_transaction_id = data.get("id")
    
    # set common field values
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

    # set metadata
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

    if data.get("balance_transaction"):
        balance_transaction = get_balance_transaction_details(data.get("balance_transaction"), api_key)

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

        billing_details = data.get("billing_details")
        if not st_doc_name and billing_details and billing_details.get("email") and data.get("receipt_url"):
            frappe.sendmail(
                recipients=[billing_details.get("email")],
                subject="Thank you for your payment",
                message=frappe.render_template(
                    "erpusa/templates/html/payment_receipt.html",
                    {
                        "receipt_url": data.get("receipt_url"),
                    },
                ),
                now=True
            )
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _('Error Saving Document'))

    if doc.status == "succeeded":
        mp_doc = create_update_merchant_payment(doc, api_key)
        metadata = doc.transaction_metadata
        if frappe.db.exists("Merchant Payment", mp_doc.name) and metadata and metadata.get('doctype') and metadata.get('docname'):
            if metadata.get('doctype') == "Sales Order":
                create_sales_invoice(metadata.get('docname'), mp_doc)
            create_payment_entry(metadata.get('doctype'), mp_doc)

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

    if data.get("balance_transaction"):
        balance_transaction = get_balance_transaction_details(data.get("balance_transaction"), api_key)

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
    
    if doc.status == "paid":
        create_journal_entry(doc)


def get_balance_transaction_details(id, api_key):
    if id:
        stripe.api_key = api_key
        try:
            balance_transaction = stripe.BalanceTransaction.retrieve(id)
            return balance_transaction
        except Exception as e:
            return {"error": str(e)}, 403

def create_update_merchant_payment(stripe_transaction, api_key):
    mp_doc_name = frappe.db.exists("Merchant Payment", {"source": stripe_transaction.stripe_transaction_id})
    if not mp_doc_name:
        mp_doc = frappe.new_doc("Merchant Payment")
    else:
        mp_doc = frappe.get_doc("Merchant Payment", mp_doc_name)
    
    balance_transaction = get_balance_transaction_details(stripe_transaction.balance_transaction, api_key)
    if balance_transaction:
        metadata = stripe_transaction.transaction_metadata
        
        mp_doc.merchant = "Stripe"
        mp_doc.merchant_transaction_id = balance_transaction.get("id")
        mp_doc.source = stripe_transaction.stripe_transaction_id
        mp_doc.merchant_fee = balance_transaction.get("fee") / 100
        mp_doc.gross_amount = balance_transaction.get("amount") / 100
        mp_doc.net_amount = balance_transaction.get("net") / 100
        mp_doc.status = balance_transaction.get("status").title()
        mp_doc.created = datetime.datetime.fromtimestamp(balance_transaction.get("created"))
        # mp_doc.created_before = datetime.datetime.fromtimestamp(balance_transaction.get("created"))
        mp_doc.available_on = datetime.datetime.fromtimestamp(balance_transaction.get("available_on"))
        mp_doc.associated_payment_request = frappe.db.exists("Payment Request", {"reference_name": metadata.get("docname")})
        
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

    if not mp_doc_name:
        notify_user(
            merchant_payment=mp_doc
        )
            
    return mp_doc

def create_sales_invoice(sales_order, merchant_payment):
    user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
    if user_to_authorize and not frappe.db.get_value("Payment Request", merchant_payment.associated_payment_request, "do_not_create_invoice"):
        frappe.set_user(user_to_authorize)
        if frappe.db.get_value("Sales Order", sales_order, "per_billed") == 0:
            si_doc = make_sales_invoice(sales_order)
            si_meta = frappe.get_meta("Sales Invoice")
            update_stock_field = next((f for f in si_meta.fields if f.fieldname == "update_stock"), None)
            if update_stock_field:
                update_stock = update_stock_field.default
            else:
                update_stock = 0
            si_doc.update_stock = update_stock
            
            try:
                si_doc.flags.ignore_permissions = True
                si_doc.save()
                si_doc.submit()
                merchant_payment.status = "Invoiced"
                merchant_payment.associated_sales_invoice = si_doc.name
                merchant_payment.save()
            except Exception as e:
                frappe.log_error(frappe.get_traceback(), _('Error Saving Document'))

def create_payment_entry(doctype, merchant_payment):
    user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
    do_not_create_invoice = frappe.db.get_value("Payment Request", merchant_payment.associated_payment_request, "do_not_create_invoice")
    if user_to_authorize:
        frappe.set_user(user_to_authorize)
        per_exists = frappe.db.exists(
            "Payment Entry Reference", 
            {
                "reference_name": merchant_payment.associated_sales_order if do_not_create_invoice else merchant_payment.associated_sales_invoice
            }
        )
        
        if not per_exists:
            pr_doc = frappe.get_doc("Payment Request", merchant_payment.associated_payment_request)
            cost_center = frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_cost_center")
            if not do_not_create_invoice:
                pr_doc.reference_doctype = "Sales Invoice"
                pr_doc.reference_name = merchant_payment.associated_sales_invoice

                si_doc = frappe.get_doc("Sales Invoice", merchant_payment.associated_sales_invoice) # get the invoice
                si_items_with_cost_center = [item for item in si_doc.items if item.cost_center] # find the items in the invoice with cost center
                max_si_item = max(si_items_with_cost_center, key=lambda item: item.net_amount) if si_items_with_cost_center else None # find the highest amount in the list
                cost_center = max_si_item.cost_center if max_si_item.cost_center else frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_cost_center")
            
            pe_doc = pr_doc.create_payment_entry(submit=frappe.db.get_single_value("Stripe Plus Settings", "auto_submit_payment"))
            pe_doc.payment_method = frappe.get_value("Payment Request", merchant_payment.associated_payment_entry, "mode_of_payment")
            pe_doc.reference_no = frappe.get_value("Stripe Transaction", merchant_payment.source, "payment_intent")
            pe_doc.paid_amount = merchant_payment.net_amount
            pe_doc.append("deductions", {
                "account": frappe.db.get_single_value("Stripe Plus Settings", "merchant_fee_account"),
                "cost_center": cost_center,
                "amount": merchant_payment.merchant_fee,
                "description": merchant_payment.name,
            })

            if get_bank_account(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, False, as_dict=False):
                pe_doc.bank_account = get_bank_account(pe_doc.payment_type, pe_doc.paid_from, pe_doc.paid_to, False, as_dict=False)

            try:
                pe_doc.flags.ignore_permissions = True
                pe_doc.save()

                merchant_payment.status = "Paid"
                merchant_payment.associated_payment_entry = pe_doc.name
                merchant_payment.save()

            except Exception as e:
                frappe.log_error(frappe.get_traceback(), _('Error Saving Document'))

def create_journal_entry(payout):
    user_to_authorize = frappe.db.get_single_value("Stripe Plus Settings", "user_to_authorize")
    if user_to_authorize:
        frappe.set_user(user_to_authorize)
        balance_transactions = stripe.BalanceTransaction.list(payout=payout.name, limit=100)
        sources = []

        # # store the sources of the payout
        for txn in balance_transactions.auto_paging_iter():
            # add the source if the transaction was accounted for
            if frappe.db.exists("Stripe Transaction", txn.source):
                sources.append({
                    "source_id": txn.source,
                    "net_amount": txn.net,
                    "currency": txn.currency,
                    "fee_details": txn.fee_details,
                    "merchant_payment": frappe.db.exists("Merchant Payment", {"source": txn.source})
                })
                frappe.set_value("Stripe Transaction", txn.source, "payout", payout.name)

        # loop through the sources to create payment entry
        for index, source in enumerate(sources):
            if source.get('merchant_payment'):
                credit_account = frappe.db.get_value(
                    "Payment Request",
                    frappe.db.get_value("Merchant Payment", source.get('merchant_payment'), "associated_payment_request"),
                    "payment_account"
                )

                credit_bank_account = frappe.db.get_value("Bank Account", {"account": credit_account}, "name")

        debit_accounts_name = frappe.db.exists("Stripe Plus Settings Payout Account", {"payout_account": payout.destination})
        if not debit_accounts_name:
            debit_accounts_name = frappe.db.exists("Stripe Plus Settings Payout Account", {"is_default_payout_account": True})

        je_doc = frappe.new_doc("Journal Entry")
        je_doc.entry_type = "Journal Entry"
        je_doc.posting_date = frappe.utils.today()
        je_doc.cheque_no = payout.name
        je_doc.cheque_date = payout.created
        je_doc.append("accounts", {
            "account": credit_account,
            "bank_account": credit_bank_account,
            "credit_in_account_currency": abs(payout.amount)
        })
        je_doc.append("accounts", {
            "account": frappe.db.get_value("Stripe Plus Settings Payout Account", debit_accounts_name, "erp_account"),
            "bank_account": frappe.db.get_value("Stripe Plus Settings Payout Account", debit_accounts_name, "erp_bank_account"),
            "debit_in_account_currency": abs(payout.amount)
        })
        
        try:
            je_doc.save()
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), _('Error Saving Document'))

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

@frappe.whitelist()
def generate_link_to_merchant_payment_list():
    schedule_ranges = find_schedule_date_ranges()
    mp = []
    dt_format = "%Y-%m-%d %H:%M:%S"
    for schedule_range in schedule_ranges:
        date_start_parameter = urllib.parse.quote(f'[">=","{schedule_range["date_start"].strftime(dt_format)}"]', safe='')
        date_end_parameter = urllib.parse.quote(f'["<=","{schedule_range["date_end"].strftime(dt_format)}"]', safe='')
        list_url = frappe.utils.get_url() + f"/app/merchant-payment?created={date_start_parameter}&created_before={date_end_parameter}"
        
        mp.append(list_url)

    return mp

@frappe.whitelist()
def notify_user(merchant_payment):
    if frappe.db.get_single_value("Stripe Plus Settings", "turn_on_email_notifications"):
        recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")
        if frappe.db.get_single_value("Stripe Plus Settings", "notification_method") == "Realtime":
            subject = f"Received {fmt_money(merchant_payment.gross_amount)} from {merchant_payment.customer}"

            frappe.sendmail(
                recipients=recipients.split(),
                subject=subject,
                message=generate_realtime_notification_email_message(
                    title=f"{merchant_payment.customer} sent {fmt_money(merchant_payment.gross_amount)}",
                    description="More information about this payment is shown below.",
                    merchant_payment=merchant_payment
                ),
                now=True
            )

        if frappe.db.get_single_value("Stripe Plus Settings", "notification_method") == "Digest":
            ranges = find_schedule_date_ranges()

            for range in ranges:
                if range["date_start"] <= merchant_payment.created <= range["date_end"]:
                    eq_docname = frappe.db.exists("Email Queue", {"send_after": range["date_end"]})
                    if eq_docname:
                        eq_doc = frappe.get_doc("Email Queue", eq_docname)
                        eq_msg = eq_doc.message
                        count = count = frappe.db.count(
                            "Merchant Payment", 
                            filters={
                                "created": ["between", [ range["date_start"], range["date_end"] ] ]
                            }
                        )

                        new_msg = re.sub(r"You have \*\*\d+\*\* new", f"You have **{count}** new", eq_msg)
                        eq_doc.message = new_msg
                        try:
                            eq_doc.save()
                        except Exception as e:
                            frappe.log_error(frappe.get_traceback(), _('Error Saving Document'))



# this section is for the detailed daily digest

def get_report_content(report, filters, no_of_rows):
    """Returns file in for the report in given format"""
    report_doc = frappe.get_doc("Report", report)


    filters = frappe.parse_json(filters) if filters else {}

    columns, data = report_doc.get_data(
        limit=no_of_rows or 100,
        user="Administrator",
        filters=filters,
        as_dict=True,
        ignore_prepared_report=True,
        are_default_filters=False,
    )

    # add serial numbers
    columns.insert(0, frappe._dict(fieldname="idx", label="", width="30px"))
    for i in range(len(data)):
        data[i]["idx"] = i + 1

    if len(data) == 0:
        return None

    columns, data = make_links(columns, data)
    columns = update_field_types(columns)

    """"
    for testing only
    """

    frappe.sendmail(
        subject="hehe",
        recipients=["mgutierrez@itgetit.com"],
        message=get_html_table(
            report="Merchant Payments",
            title="Title",
            description="Description",
            report_type="Script Report",
            columns=columns,
            data=data
        ),
        now=True
    )
    return get_html_table(
        report="Merchant Payments",
        title="Title",
        description="Description",
        report_type="Script Report",
        columns=columns,
        data=data
    )

def get_html_table(report, title, description, report_type, columns=None, data=None):
    date_time = global_date_format(now()) + " " + format_time(now())
    report_doctype = frappe.db.get_value("Report", report, "ref_doctype")

    return frappe.render_template(
        "erpusa/templates/html/daily_digest_detailed.html",
        {
            "title": title,
            "description": description,
            "date_time": date_time,
            "columns": columns,
            "data": data,
            "report_url": get_url_to_report(report, report_type, report_doctype),
            "report_name": report,
        },
    )
            

	
	
