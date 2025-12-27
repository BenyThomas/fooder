import secrets
import frappe
from frappe import _
from frappe.utils import now_datetime

def _resp_ok(data=None, message="OK"):
    return {"status": "success", "message": message, "data": data or {}}

def _resp_fail(message="Failed", data=None):
    return {"status": "fail", "message": message, "data": data or {}}

def _get_token_doc(token: str):
    return frappe.get_all(
        "Table QR Token",
        filters={"token": token},
        fields=["name", "restaurant", "restaurant_table", "is_enabled", "qr_url"]
    )

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
    menu_name = None
    for f in ("is_active", "active"):
        menu_name = frappe.get_value("Restaurant Menu", {"restaurant": t["restaurant"], f: 1}, "name")
        if menu_name:
            break
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
        return _resp_ok({"order_number": existing}, "Already placed")

    t = _get_token_doc(token)
    if not t:
        return _resp_fail("Invalid QR token")
    t = t[0]
    if not t.get("is_enabled"):
        return _resp_fail("Table unavailable")

    # Active menu (same logic as get_menu)
    menu_name = None
    for f in ("is_active", "active"):
        menu_name = frappe.get_value("Restaurant Menu", {"restaurant": t["restaurant"], f: 1}, "name")
        if menu_name:
            break
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
        "items": [
            {"doctype": "Guest Order Item", "item": l["item"], "qty": l["qty"], "rate": l["rate"], "amount": l["amount"]}
            for l in lines
        ],
        "status_log": [{
            "doctype": "Guest Order Status Log",
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

    return _resp_ok({"order_number": go.name, "sales_invoice": si.name}, "Order placed")

@frappe.whitelist()
def generate_table_qr(restaurant: str, restaurant_table: str):
    token = secrets.token_urlsafe(24)
    qr_url = f"{frappe.utils.get_url()}/fooder/{token}"

    doc = frappe.get_doc({
        "doctype": "QR token",
        "restaurant": restaurant,
        "restaurant_table": restaurant_table,
        "token": token,
        "is_enabled": 1,
        "qr_url": qr_url,
        "last_generated_on": now_datetime()
    })
    doc.insert()

    # For demo: store URL; optionally generate image later
    return _resp_ok({"token": token, "qr_url": qr_url, "docname": doc.name}, "QR generated")

@frappe.whitelist()
def disable_table_qr(token_docname: str):
    doc = frappe.get_doc("Table QR Token", token_docname)
    doc.is_enabled = 0
    doc.save()
    return _resp_ok({}, "QR disabled")


