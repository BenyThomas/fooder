import frappe
from frappe import _
from frappe.utils import now_datetime
from fooder.integrations.restaurant_table_events import (
    TABLE_QR_DOCTYPE,
    _create_qr_token,
    _disable_active_tokens,
)

def _resp_ok(data=None, message="OK"):
    return {"status": "success", "message": message, "data": data or {}}

def _resp_fail(message="Failed", data=None):
    return {"status": "fail", "message": message, "data": data or {}}


def _serialize_items(rows):
    return [
        {
            "item_code": row.item,
            "qty": float(row.qty or 0),
            "rate": float(row.rate or 0),
            "amount": float(row.amount or 0),
            "notes": getattr(row, "item_notes", None),
        }
        for row in rows
    ]


def _serialize_status_log(rows):
    return [
        {
            "from": row.from_status,
            "to": row.status,
            "changed_on": row.changed_on,
            "changed_by": row.changed_by,
            "note": getattr(row, "note", None),
        }
        for row in rows
    ]


def _build_order_payload(go):
    table = frappe.get_doc("Restaurant Table", go.restaurant_table)
    table_label = getattr(table, "table_identifier", None) or table.name

    return {
        "name": go.name,
        "display_order_no": go.display_order_no,
        "order_number": go.display_order_no,
        "tracking_token": go.tracking_token,
        "tracking_code": go.tracking_token,
        "restaurant": go.restaurant,
        "restaurant_table": go.restaurant_table,
        "table_label": table_label,
        "status": go.status,
        "notes": go.notes,
        "language": go.language,
        "created_on": go.creation,
        "items": _serialize_items(go.guest_order_items or []),
        "status_log": _serialize_status_log(go.guest_order_status_log or []),
        "total": sum(float(row.amount or 0) for row in (go.guest_order_items or [])),
    }


def _get_order_by_tracking(tracking_token: str):
    name = frappe.get_value("Guest Order", {"tracking_token": tracking_token}, "name")
    return frappe.get_doc("Guest Order", name) if name else None

def _get_token_doc(token: str):
    return frappe.get_all(
        TABLE_QR_DOCTYPE,
        filters={"token": token},
        fields=["name", "restaurant", "restaurant_table", "is_enabled", "qr_url"]
    )


def _get_active_menu_name(restaurant: str):
    """Return the active menu for a restaurant while tolerating missing fields.

    Some deployments use a custom ``is_active`` flag, others use ``active``, and
    older databases might not have either. Check which fields actually exist
    before filtering to avoid ``Unknown column`` SQL errors and fall back to the
    first menu for the restaurant when none of the flags are present.
    """

    meta = frappe.get_meta("Restaurant Menu")
    active_fields = [f for f in ("is_active", "active","enabled") if meta.has_field(f)]

    for f in active_fields:
        name = frappe.get_value("Restaurant Menu", {"restaurant": restaurant, f: 1}, "name")
        if name:
            return name

    # Fallback: any menu for the restaurant
    return frappe.get_value("Restaurant Menu", {"restaurant": restaurant}, "name")

@frappe.whitelist(allow_guest=True)
def get_menu(token: str, lang: str = "en"):
    if not token:
        return _resp_fail("Missing token")

    t = _get_token_doc(token)
    if not t:
        return _resp_fail("Invalid QR token")
    t = t[0]
    if not t.get("is_enabled"):
        return _resp_fail("Table unavailable")

    # Table active check (custom field on Restaurant Table)
    table = frappe.get_doc("Restaurant Table", t["restaurant_table"])
    if hasattr(table, "is_active") and not table.is_active:
        return _resp_fail("Table unavailable")

    # Find active menu for the restaurant (field name may differ; handle both)
    menu_name = _get_active_menu_name(t["restaurant"])
    if not menu_name:
        return _resp_fail("No active menu found")

    menu = frappe.get_doc("Restaurant Menu", menu_name)

    # Most v14 setups have 'items' child table and a linked price list created on save :contentReference[oaicite:4]{index=4}
    price_list = getattr(menu, "price_list", None)

    out_items = []
    for row in (menu.items or []):
        # Availability control (custom field on child row)
        if hasattr(row, "is_available") and not row.is_available:
            continue

        item = frappe.get_doc("Item", row.item)
        display_name = item.item_name
        description = item.description or ""

        if (lang or "en").lower() == "sw":
            display_name = getattr(item, "item_name_sw", None) or display_name
            description = getattr(item, "description_sw", None) or description

        # Rate: prefer row.rate if present; else try Item Price from menu's price list
        rate = getattr(row, "rate", None)
        if (rate is None) and price_list:
            rate = frappe.get_value("Item Price", {"price_list": price_list, "item_code": item.item_code}, "price_list_rate")

        out_items.append({
            "item_code": item.item_code,
            "display_name": display_name,
            "description": description,
            "rate": float(rate or 0),
            "image": item.image or None
        })

    return _resp_ok({
        "restaurant": t["restaurant"],
        "table": table.get("table_identifier") if hasattr(table, "table_identifier") else table.name,
        "menu": menu.name,
        "price_list": price_list,
        "items": out_items
    })

@frappe.whitelist(allow_guest=True)
def place_order(token: str, client_order_id: str, items: list, notes: str = None, lang: str = "en"):
    if not token:
        return _resp_fail("Missing token")
    if not client_order_id:
        return _resp_fail("Missing client_order_id")
    if not items:
        return _resp_fail("No items")

    # Idempotency
    existing = frappe.get_value("Guest Order", {"client_order_id": client_order_id}, "name")
    if existing:
        go = frappe.get_doc("Guest Order", existing)
        return _resp_ok(_build_order_payload(go), "Already placed")

    t = _get_token_doc(token)
    if not t:
        return _resp_fail("Invalid QR token")
    t = t[0]
    if not t.get("is_enabled"):
        return _resp_fail("Table unavailable")

    # Active menu (same logic as get_menu)
    menu_name = _get_active_menu_name(t["restaurant"])
    if not menu_name:
        return _resp_fail("No active menu found")

    menu = frappe.get_doc("Restaurant Menu", menu_name)
    price_list = getattr(menu, "price_list", None)

    # Build safe priced items (server-side pricing)
    item_map = {}
    for r in (menu.items or []):
        if hasattr(r, "is_available") and not r.is_available:
            continue
        item_map[r.item] = r

    lines = []
    for it in items:
        code = it.get("item_code")
        qty = float(it.get("qty") or 0)
        if not code or qty <= 0:
            continue
        if code not in item_map:
            return _resp_fail(f"Item not available: {code}")

        row = item_map[code]
        rate = getattr(row, "rate", None)
        if (rate is None) and price_list:
            rate = frappe.get_value("Item Price", {"price_list": price_list, "item_code": code}, "price_list_rate")
        rate = float(rate or 0)
        lines.append({"item": code, "qty": qty, "rate": rate, "amount": rate * qty})

    if not lines:
        return _resp_fail("No valid items")

    # Create Guest Order
    go = frappe.get_doc({
        "doctype": "Guest Order",
        "restaurant": t["restaurant"],
        "restaurant_table": t["restaurant_table"],
        "token": token,
        "client_order_id": client_order_id,
        "language": (lang or "en").lower(),
        "notes": notes,
        "status": "Placed",
        "guest_order_items": [
            {"doctype": "Guest Order Item", "item": l["item"], "qty": l["qty"], "rate": l["rate"], "amount": l["amount"]}
            for l in lines
        ],
        "guest_order_status_log": [{
            "doctype": "Guest Order Status Log",
            "from_status": None,
            "status": "Placed",
            "changed_on": now_datetime(),
            "changed_by": "Guest"
        }]
    })
    go.insert(ignore_permissions=True)

    # Create draft Sales Invoice for billing (MVP)
    restaurant_doc = frappe.get_doc("Restaurant", t["restaurant"])
    customer = restaurant_doc.default_customer

    si = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": customer,
        "set_posting_time": 1,
        "posting_date": frappe.utils.today(),
        "items": [{"item_code": l["item"], "qty": l["qty"], "rate": l["rate"]} for l in lines],
    })
    # optional: set taxes template from Restaurant :contentReference[oaicite:5]{index=5}
    if getattr(restaurant_doc, "default_sales_taxes_and_charges_template", None):
        si.taxes_and_charges = restaurant_doc.default_sales_taxes_and_charges_template

    si.insert(ignore_permissions=True)
    go.sales_invoice = si.name
    go.save(ignore_permissions=True)

    go.reload()
    return _resp_ok(_build_order_payload(go), "Order placed")


@frappe.whitelist(allow_guest=True)
def get_order(tracking_token: str = None, order_name: str = None):
    """Return a guest-order summary for confirmation or tracking pages."""

    go = None
    if tracking_token:
        go = _get_order_by_tracking(tracking_token)
    elif order_name:
        go = frappe.get_doc("Guest Order", order_name)

    if not go:
        return _resp_fail("Order not found")

    return _resp_ok(_build_order_payload(go))


ALLOWED_STATUSES = {"Placed", "Accepted", "Preparing", "Ready", "Served", "Cancelled"}
LINEAR_TRANSITIONS = {
    "Placed": {"Accepted"},
    "Accepted": {"Preparing"},
    "Preparing": {"Ready"},
    "Ready": {"Served"},
}


@frappe.whitelist()
def update_order_status(order_name: str, status: str, note: str | None = None):
    """Update an order status and append the audit trail."""

    if not status or status not in ALLOWED_STATUSES:
        return _resp_fail("Invalid status")

    go = frappe.get_doc("Guest Order", order_name)
    previous = go.status

    if previous == status:
        return _resp_ok(_build_order_payload(go), "No status change")

    if status != "Cancelled":
        allowed_next = LINEAR_TRANSITIONS.get(previous, set())
        if status not in allowed_next:
            return _resp_fail("Transition not allowed")

    go.append(
        "guest_order_status_log",
        {
            "doctype": "Guest Order Status Log",
            "from_status": previous,
            "status": status,
            "changed_on": now_datetime(),
            "changed_by": frappe.session.user,
            "note": note,
        },
    )

    # Avoid duplicate logging from DocType hooks
    go.flags.skip_status_log = True
    go.status = status
    go.save(ignore_permissions=True)
    go.reload()

    return _resp_ok(_build_order_payload(go), "Status updated")

@frappe.whitelist()
def generate_table_qr(restaurant: str, restaurant_table: str):
    doc = _create_qr_token(restaurant, restaurant_table)
    return _resp_ok({"token": doc["token"], "qr_url": doc["qr_url"], "docname": doc["name"]}, "QR generated")

@frappe.whitelist()
def disable_table_qr(token_docname: str):
    doc = frappe.get_doc(TABLE_QR_DOCTYPE, token_docname)
    _disable_active_tokens(doc.restaurant_table)
    frappe.db.set_value(TABLE_QR_DOCTYPE, doc.name, "is_enabled", 0)
    return _resp_ok({}, "QR disabled")


