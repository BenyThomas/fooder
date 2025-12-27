import frappe


def execute():
    if not frappe.db.table_exists("Workspace"):
        return

    workspace = frappe.db.exists("Workspace", {"name": "Kitchen"}) or frappe.db.exists(
        "Workspace", {"title": "Kitchen"}
    )

    if not workspace:
        return

    workspace_doc = frappe.get_doc("Workspace", workspace)

    shortcuts_changed = False
    for shortcut in workspace_doc.get("shortcuts", []):
        if shortcut.get("type") and shortcut.get("type") != "Link":
            shortcut.type = "Link"
            shortcuts_changed = True

        if shortcut.meta.get_field("link_type") and shortcut.link_type:
            shortcut.link_type = None
            shortcuts_changed = True

        if shortcut.meta.get_field("link_to") and shortcut.link_to != "/kitchen":
            shortcut.link_to = "/kitchen"
            shortcuts_changed = True

    if shortcuts_changed:
        workspace_doc.save(ignore_permissions=True)
