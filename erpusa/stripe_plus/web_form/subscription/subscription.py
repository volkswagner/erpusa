import frappe

def get_context(context):
	context.data = frappe.form_dict
