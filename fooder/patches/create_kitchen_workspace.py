import frappe


KITCHEN_WORKSPACE_NAME = "Kitchen"


def execute():
    """Create a Kitchen workspace with a shortcut to the web kitchen view."""
    if not frappe.db.table_exists("Workspace"):
        return

    # Avoid duplication when the workspace already exists.
    if frappe.db.exists("Workspace", KITCHEN_WORKSPACE_NAME) or frappe.db.exists(
        "Workspace", {"title": KITCHEN_WORKSPACE_NAME}
    ):
        return

    workspace_meta = frappe.get_meta("Workspace")
    shortcut_meta = frappe.get_meta("Workspace Shortcut") if frappe.db.table_exists(
        "Workspace Shortcut"
    ) else None

    workspace = frappe.new_doc("Workspace")
    workspace.name = KITCHEN_WORKSPACE_NAME

    if workspace_meta.has_field("title"):
        workspace.title = KITCHEN_WORKSPACE_NAME
    if workspace_meta.has_field("label"):
        workspace.label = KITCHEN_WORKSPACE_NAME
    if workspace_meta.has_field("module"):
        workspace.module = "Fooder"
    if workspace_meta.has_field("category"):
        workspace.category = "Modules"
    if workspace_meta.has_field("public"):
        workspace.public = 1
    if workspace_meta.has_field("is_hidden"):
        workspace.is_hidden = 0
    if workspace_meta.has_field("parent_page"):
        workspace.parent_page = "Modules"
    if workspace_meta.has_field("is_default"):
        workspace.is_default = 0

    if shortcut_meta:
        shortcut_row = {}
        if shortcut_meta.has_field("label"):
            shortcut_row["label"] = "Kitchen Orders"
        if shortcut_meta.has_field("type"):
            shortcut_row["type"] = "URL"
        if shortcut_meta.has_field("link_type"):
            shortcut_row["link_type"] = "URL"
        if shortcut_meta.has_field("link_to"):
            shortcut_row["link_to"] = "/kitchen"
        if shortcut_meta.has_field("description"):
            shortcut_row["description"] = "Monitor guest orders from the Fooder kitchen screen."
        if shortcut_row:
            workspace.append("shortcuts", shortcut_row)

    # In some versions, the shortcut's dynamic link validation expects a DocType named
    # after the provided link_type ("URL" in our case). That DocType might not exist in
    # older site states, which would cause the migration to fail. Ignore link validation
    # so the workspace can be created regardless of DocType availability.
    workspace.insert(
        ignore_permissions=True, ignore_if_duplicate=True, ignore_links=True
    )
