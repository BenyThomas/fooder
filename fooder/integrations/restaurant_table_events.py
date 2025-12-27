import secrets
from typing import Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import get_url, now_datetime

TABLE_QR_DOCTYPE = "QR token"


def _generate_unique_token() -> str:
    """Generate a unique, URL-safe token that does not clash with existing QR tokens."""
    while True:
        token = secrets.token_urlsafe(20)
        if not frappe.db.exists(TABLE_QR_DOCTYPE, {"token": token}):
            return token


def _build_qr_url(token: str) -> str:
    # Point the QR directly to the public guest ordering page with the token prefilled
    # so visitors land on a valid route. Previously this pointed to `/fooder/<token>`
    # which isn't a real page and resulted in a 500 error from an unrelated order view.
    return f"{get_url()}/guest_order?token={token}"


def _get_active_token_for_table(restaurant_table: str) -> Optional[Dict]:
    return frappe.db.get_value(
        TABLE_QR_DOCTYPE,
        {"restaurant_table": restaurant_table, "is_enabled": 1},
        ["name", "restaurant", "restaurant_table", "token", "qr_url", "last_generated_on", "modified", "creation"],
        as_dict=True,
        order_by="creation desc",
    )


def _get_token_history(restaurant_table: str) -> List[Dict]:
    return frappe.get_all(
        TABLE_QR_DOCTYPE,
        filters={"restaurant_table": restaurant_table},
        fields=["name", "token", "qr_url", "is_enabled", "last_generated_on", "modified", "creation"],
        order_by="creation desc",
    )


def _create_qr_token(restaurant: str, restaurant_table: str) -> Dict:
    token = _generate_unique_token()
    qr_url = _build_qr_url(token)

    doc = frappe.get_doc({
        "doctype": TABLE_QR_DOCTYPE,
        "restaurant": restaurant,
        "restaurant_table": restaurant_table,
        "token": token,
        "is_enabled": 1,
        "qr_url": qr_url,
        "last_generated_on": now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    return doc.as_dict()


def _disable_active_tokens(restaurant_table: str):
    active_tokens = frappe.get_all(
        TABLE_QR_DOCTYPE,
        filters={"restaurant_table": restaurant_table, "is_enabled": 1},
        pluck="name",
    )
    for name in active_tokens:
        frappe.db.set_value(TABLE_QR_DOCTYPE, name, "is_enabled", 0)


@frappe.whitelist()
def ensure_qr_after_save(doc, method=None):
    """Ensure every active Restaurant Table has an active QR token."""
    if getattr(doc, "is_active", True) is False:
        frappe.msgprint(_("Table is inactive. QR token was not generated."), indicator="orange")
        return

    if not getattr(doc, "restaurant", None):
        frappe.msgprint(_("Restaurant is required to generate a QR token."), indicator="red")
        return

    if _get_active_token_for_table(doc.name):
        return

    created = _create_qr_token(doc.restaurant, doc.name)
    frappe.msgprint(
        _("QR token created: {0}").format(created["token"]) + f"\n{created['qr_url']}",
        indicator="green",
    )


@frappe.whitelist()
def get_table_qr_info(restaurant_table: str):
    if not restaurant_table:
        frappe.throw(_("Missing restaurant table"))

    active = _get_active_token_for_table(restaurant_table)
    history = _get_token_history(restaurant_table)
    return {"active": active, "history": history}


@frappe.whitelist()
def regenerate_table_qr(restaurant_table: str):
    if not restaurant_table:
        frappe.throw(_("Missing restaurant table"))

    table = frappe.get_doc("Restaurant Table", restaurant_table)
    if getattr(table, "is_active", True) is False:
        frappe.throw(_("Table is inactive. Activate the table before regenerating a QR token."))

    _disable_active_tokens(restaurant_table)
    created = _create_qr_token(table.restaurant, restaurant_table)

    return {"active": created, "history": _get_token_history(restaurant_table)}


@frappe.whitelist()
def disable_table_qr(restaurant_table: str):
    if not restaurant_table:
        frappe.throw(_("Missing restaurant table"))

    active = _get_active_token_for_table(restaurant_table)
    if not active:
        frappe.throw(_("No active QR token found for this table."))

    frappe.db.set_value(TABLE_QR_DOCTYPE, active["name"], "is_enabled", 0)
    return {"active": None, "history": _get_token_history(restaurant_table)}
