import frappe

def get_context(context):
    context.no_cache = 1
    context.token = frappe.form_dict.get("token")
    return context
