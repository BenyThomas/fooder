import frappe

def execute():
    # "Top Bar Item" exists in ERPNext website settings
    if not frappe.db.exists("DocType", "Top Bar Item"):
        return

    # Prevent duplicates
    if frappe.db.exists("Top Bar Item", {"url": "/kitchen"}):
        return

    item = frappe.get_doc({
        "doctype": "Top Bar Item",
        "label": "Kitchen",
        "url": "/kitchen",
        "right": 0,
        "parenttype": "Website Settings",
        "parentfield": "top_bar_items",
        "parent": "Website Settings",
    })
    item.insert(ignore_permissions=True)
    frappe.db.commit()
