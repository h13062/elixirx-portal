"""Notification helper — consolidates inserts into the `notifications` table.

Used by routers that emit notifications (warranty, reservations, issues,
machine_lifecycle, ...). All functions are synchronous because the Supabase
Python client is synchronous.

Notifications table schema (Sprint 3 Task 3.0 migration):
    id, user_id, title, message, type, entity_type, entity_id, is_read, created_at

NOTE: the column is `is_read`, not `read`. Earlier router code wrote `read`
which was silently dropped by the try/except wrapper around the insert — the
notification never made it to the table. Always use this helper.
"""

from typing import Optional

from app.core.supabase_client import supabase_admin


def create_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "general",
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> dict | None:
    """Insert a single notification for one user. Returns the row, or None on failure."""
    try:
        result = supabase_admin.table("notifications").insert({
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notification_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "is_read": False,
        }).execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


def notify_admins(
    title: str,
    message: str,
    notification_type: str = "general",
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> int:
    """Send the same notification to every active admin/super_admin. Returns count sent."""
    try:
        admins = (
            supabase_admin.table("profiles")
            .select("id")
            .in_("role", ["admin", "super_admin"])
            .eq("account_status", "active")
            .execute()
            .data
            or []
        )
    except Exception:
        return 0

    sent = 0
    for a in admins:
        if create_notification(
            a["id"], title, message, notification_type, entity_type, entity_id
        ):
            sent += 1
    return sent


def notify_user(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "general",
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> dict | None:
    """Send notification to a specific user. Thin wrapper for naming symmetry."""
    return create_notification(
        user_id, title, message, notification_type, entity_type, entity_id
    )
