import frappe

def get_context(context):
    context.no_cache = 1
    context.tracking_token = frappe.form_dict.get("tracking_token")
    context.polling_seconds = 10
    return context
