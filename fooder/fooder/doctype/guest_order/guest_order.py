# Copyright (c) 2025, Zendela Technologies ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, today


def _sanitize_prefix(value: str) -> str:
    """Create a short alphanumeric prefix for the display number."""

    cleaned = "".join(ch for ch in (value or "") if ch.isalnum())
    return cleaned[:3].upper() or "ORD"


def generate_display_order_no(restaurant: str, restaurant_table: str) -> str:
    """Generate a memorable order number scoped to a restaurant and day.

    The format is ``<TAB>-<YYMMDD>-<###>`` where the sequence resets each day
    per restaurant. ``TAB`` is derived from the table identifier (or table
    name) to keep the number memorable for guests and staff.
    """

    table_identifier = frappe.get_value(
        "Restaurant Table", restaurant_table, "table_identifier"
    ) or restaurant_table

    prefix = _sanitize_prefix(table_identifier)
    date_part = now_datetime().strftime("%y%m%d")

    # Lock the counter for the restaurant for today to avoid duplicates when
    # multiple orders arrive at the same time.
    current_seq = frappe.db.sql(
        """
        select count(*)
        from `tabGuest Order`
        where restaurant=%s and date(creation)=%s
        for update
        """,
        (restaurant, today()),
    )[0][0]

    return f"{prefix}-{date_part}-{current_seq + 1:03d}"


class GuestOrder(Document):
    def before_insert(self):
        if not getattr(self, "tracking_token", None):
            self.tracking_token = frappe.generate_hash(length=12)

        if not getattr(self, "display_order_no", None):
            self.display_order_no = generate_display_order_no(
                self.restaurant, self.restaurant_table
            )
