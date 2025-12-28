import frappe

KITCHEN_WORKSPACE_NAME = "Kitchen"
KITCHEN_PAGE_NAME = "kitchen-page"
REQUIRED_ROLES = ("Hospitality User", "Hotel Manager", "Restaurant Manager")
KITCHEN_URL = "/kitchen"


def _sync_roles(doc):
    """Ensure the document has the expected roles and remove typos."""
    if not hasattr(doc, "roles"):
        return False

    changed = False
    clean_roles = []
    seen = set()

    for row in doc.roles or []:
        role = getattr(row, "role", None)
        if role == "Hospitslity user":
            changed = True
            continue
        if role:
            seen.add(role)
        clean_roles.append(row)

    if len(clean_roles) != len(doc.roles or []):
        changed = True

    doc.roles = clean_roles

    for role in REQUIRED_ROLES:
        if role not in seen:
            doc.append("roles", {"role": role})
            seen.add(role)
            changed = True

    return changed


def execute():
    """Fix Kitchen workspace/page visibility and shortcut behaviour."""
    # Workspace adjustments
    if frappe.db.table_exists("Workspace"):
        ws_name = (
            frappe.db.get_value("Workspace", KITCHEN_WORKSPACE_NAME, "name")
            or frappe.db.get_value("Workspace", {"title": KITCHEN_WORKSPACE_NAME}, "name")
            or frappe.db.get_value("Workspace", {"label": KITCHEN_WORKSPACE_NAME}, "name")
        )

        if ws_name:
            workspace = frappe.get_doc("Workspace", ws_name)
            changed = _sync_roles(workspace)

            for sc in workspace.shortcuts or []:
                if (getattr(sc, "label", "") or "").strip() != "Kitchen Orders":
                    continue

                if hasattr(sc, "type"):
                    sc.type = "URL"
                if hasattr(sc, "url"):
                    sc.url = KITCHEN_URL

                for fn in ("link_type", "link_to", "doctype", "doc_type", "document_type"):
                    if hasattr(sc, fn):
                        setattr(sc, fn, None)

                changed = True

            if changed:
                workspace.flags.ignore_links = True
                workspace.save(ignore_permissions=True)
                frappe.db.commit()

    # Page role cleanup
    if frappe.db.table_exists("Page") and frappe.db.exists("Page", KITCHEN_PAGE_NAME):
        page = frappe.get_doc("Page", KITCHEN_PAGE_NAME)
        if _sync_roles(page):
            page.save(ignore_permissions=True)
            frappe.db.commit()
