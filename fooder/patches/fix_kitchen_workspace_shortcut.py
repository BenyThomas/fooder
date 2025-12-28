import frappe

KITCHEN_WORKSPACE_NAME = "Kitchen"
KITCHEN_URL = "/kitchen"

def execute():
    if not frappe.db.table_exists("Workspace"):
        return

    ws_name = (
        frappe.db.get_value("Workspace", KITCHEN_WORKSPACE_NAME, "name")
        or frappe.db.get_value("Workspace", {"title": KITCHEN_WORKSPACE_NAME}, "name")
        or frappe.db.get_value("Workspace", {"label": KITCHEN_WORKSPACE_NAME}, "name")
    )
    if not ws_name:
        return

    workspace = frappe.get_doc("Workspace", ws_name)

    shortcut_meta = frappe.get_meta("Workspace Shortcut")
    fields = {df.fieldname for df in shortcut_meta.fields}

    changed = False
    for sc in (workspace.shortcuts or []):
        if (getattr(sc, "label", "") or "").strip() != "Kitchen Orders":
            continue

        # Ensure shortcut is URL-type
        if "type" in fields:
            sc.type = "URL"

        # IMPORTANT: set URL into a plain data field (prefer `url`)
        if "url" in fields:
            sc.url = KITCHEN_URL

        # Clear any fields that can trigger link validation
        # (names vary by version/customizations)
        for fn in ("link_type", "link_to", "doctype", "doc_type", "document_type"):
            if fn in fields:
                setattr(sc, fn, None)

        changed = True

    if changed:
        # Bypass link validation (this is what is failing)
        workspace.flags.ignore_links = True
        workspace.save(ignore_permissions=True)
        frappe.db.commit()
