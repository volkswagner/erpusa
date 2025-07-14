import frappe

def create_docs_payment_methods():
    payment_methods =  {
        "acss_debit": "Pre-authorized Debit Payments",
        "affirm": "Affirm",
        "afterpay_clearpay": "Afterpay / Clearpay",
        "alipay": "Alipay",
        "amazon_pay": "Amazon Pay",
        "apple_pay": "Apple Pay",
        "apple_pay_later": "Apple Pay Later",
        "bacs_debit": "Bacs Direct Debit",
        "bancontact": "Bancontact",
        "blik": "BLIK",
        "card": "Card Payments",
        "cashapp": "Cash App Pay",
        "eps": "EPS",
        "giropay": "Giropay",
        "google_pay": "Google Pay",
        "ideal": "iDEAL",
        "kakao_pay": "Kakao Pay",
        "klarna": "Klarna",
        "kr_card": "Korean Cards",
        "link": "Link",
        "multibanco": "Multibanco",
        "naver_pay": "Naver Pay",
        "p24": "Przelewy24",
        "payco": "PAYCO",
        "pix": "Pix",
        "samsung_pay": "Samsung Pay",
        "sepa_debit": "SEPA Direct Debit",
        "sofort": "Sofort",
        "us_bank_account": "ACH Direct Debit",
        "wechat_pay": "WeChat Pay",
        "zip": "Zip"
    }

    for method_code, method_name in payment_methods.items():
        if not frappe.db.exists("Stripe Payment Method", {"payment_method_code": method_code}):
            doc = frappe.get_doc({
                "doctype": "Stripe Payment Method",
                "payment_method_name": method_name,
                "payment_method_code": method_code,
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()