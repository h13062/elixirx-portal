"""Notifications router (Sprint 3 Task 3.5).

Endpoints for the notification bell + admin broadcast. Direct supabase_admin
queries — no service/repository per spec.

Authorization summary:
- All read/modify-own endpoints: any logged-in user, scoped to their own user_id
- POST /api/notifications: admin only (create for any user)
- POST /api/notifications/broadcast: admin only

Route ordering: static segments (`/notifications/unread-count`,
`/notifications/read-all`, `/notifications/clear-read`,
`/notifications/broadcast`) MUST be declared before
`/notifications/{notification_id}` so FastAPI doesn't capture literals as the
dynamic param.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user, require_admin
from app.core.notification_helper import create_notification
from app.core.supabase_client import supabase_admin
from app.models.inventory_models import (
    NotificationBroadcastRequest,
    NotificationCreateRequest,
    NotificationResponse,
)

router = APIRouter(prefix="/api", tags=["Notifications"])

VALID_ROLE_FILTERS = ("admin", "rep", "all")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_owned_or_403(notification_id: str, current_user: dict) -> dict:
    """Fetch a notification, 404 if missing, 403 if not owned by current user."""
    r = (
        supabase_admin.table("notifications")
        .select("*")
        .eq("id", notification_id)
        .execute()
    )
    if not r.data:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    row = r.data[0]
    if row["user_id"] != current_user["id"]:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="This notification doesn't belong to you",
        )
    return row


# ---------------------------------------------------------------------------
# GET /api/notifications  (current user's notifications)
# ---------------------------------------------------------------------------

@router.get("/notifications", response_model=list[NotificationResponse])
def list_my_notifications(
    is_read: bool | None = Query(default=None),
    type_filter: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    try:
        q = (
            supabase_admin.table("notifications")
            .select("*")
            .eq("user_id", current_user["id"])
            .order("created_at", desc=True)
        )
        if is_read is not None:
            q = q.eq("is_read", is_read)
        if type_filter:
            q = q.eq("type", type_filter)
        # range(start, end) is inclusive on both ends
        q = q.range(offset, offset + limit - 1)
        return q.execute().data or []
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch notifications: {e}",
        )


# ---------------------------------------------------------------------------
# POST /api/notifications  (admin only — create for any user)
# ---------------------------------------------------------------------------

@router.post(
    "/notifications", response_model=NotificationResponse, status_code=201
)
def admin_create_notification(
    payload: NotificationCreateRequest,
    current_user: dict = Depends(require_admin),
):
    try:
        created = create_notification(
            user_id=payload.user_id,
            title=payload.title,
            message=payload.message,
            notification_type=payload.type or "general",
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
        )
        if not created:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create notification",
            )
        return created
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create notification: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/notifications/unread-count  (static — before /{id})
# ---------------------------------------------------------------------------

@router.get("/notifications/unread-count")
def unread_count(current_user: dict = Depends(get_current_user)):
    try:
        r = (
            supabase_admin.table("notifications")
            .select("id", count="exact")
            .eq("user_id", current_user["id"])
            .eq("is_read", False)
            .execute()
        )
        return {"count": r.count or 0}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch unread count: {e}",
        )


# ---------------------------------------------------------------------------
# PUT /api/notifications/read-all  (static — before /{id})
# ---------------------------------------------------------------------------

@router.put("/notifications/read-all")
def mark_all_read(current_user: dict = Depends(get_current_user)):
    try:
        # Count first (for the response)
        r = (
            supabase_admin.table("notifications")
            .select("id", count="exact")
            .eq("user_id", current_user["id"])
            .eq("is_read", False)
            .execute()
        )
        count = r.count or 0

        if count > 0:
            supabase_admin.table("notifications").update({
                "is_read": True,
            }).eq("user_id", current_user["id"]).eq("is_read", False).execute()

        return {"updated": count}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark all as read: {e}",
        )


# ---------------------------------------------------------------------------
# DELETE /api/notifications/clear-read  (static — before /{id})
# ---------------------------------------------------------------------------

@router.delete("/notifications/clear-read")
def clear_read(current_user: dict = Depends(get_current_user)):
    try:
        r = (
            supabase_admin.table("notifications")
            .select("id", count="exact")
            .eq("user_id", current_user["id"])
            .eq("is_read", True)
            .execute()
        )
        count = r.count or 0

        if count > 0:
            (
                supabase_admin.table("notifications")
                .delete()
                .eq("user_id", current_user["id"])
                .eq("is_read", True)
                .execute()
            )

        return {"deleted": count}
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear read notifications: {e}",
        )


# ---------------------------------------------------------------------------
# POST /api/notifications/broadcast  (admin only — static, before /{id})
# ---------------------------------------------------------------------------

@router.post("/notifications/broadcast")
def broadcast_notification(
    payload: NotificationBroadcastRequest,
    current_user: dict = Depends(require_admin),
):
    try:
        role = (payload.role_filter or "all").lower()
        if role not in VALID_ROLE_FILTERS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid role_filter '{role}'. "
                    f"Allowed: {list(VALID_ROLE_FILTERS)}"
                ),
            )

        q = (
            supabase_admin.table("profiles")
            .select("id")
            .eq("account_status", "active")
        )
        if role == "admin":
            q = q.in_("role", ["admin", "super_admin"])
        elif role == "rep":
            q = q.eq("role", "rep")
        # role == "all" → no role filter

        users = q.execute().data or []

        sent = 0
        for u in users:
            if create_notification(
                user_id=u["id"],
                title=payload.title,
                message=payload.message,
                notification_type=payload.type or "general",
            ):
                sent += 1

        return {"sent_to": sent}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to broadcast: {e}",
        )


# ---------------------------------------------------------------------------
# PUT /api/notifications/{notification_id}/read  (3-seg, before /{id})
# ---------------------------------------------------------------------------

@router.put(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
)
def mark_read(
    notification_id: str, current_user: dict = Depends(get_current_user)
):
    try:
        _get_owned_or_403(notification_id, current_user)
        supabase_admin.table("notifications").update({
            "is_read": True,
        }).eq("id", notification_id).execute()
        refreshed = (
            supabase_admin.table("notifications")
            .select("*")
            .eq("id", notification_id)
            .execute()
        )
        if not refreshed.data:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Notification updated but could not be retrieved",
            )
        return refreshed.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark notification as read: {e}",
        )


# ---------------------------------------------------------------------------
# DELETE /api/notifications/{notification_id}
# ---------------------------------------------------------------------------

@router.delete("/notifications/{notification_id}")
def delete_notification(
    notification_id: str, current_user: dict = Depends(get_current_user)
):
    try:
        _get_owned_or_403(notification_id, current_user)
        (
            supabase_admin.table("notifications")
            .delete()
            .eq("id", notification_id)
            .execute()
        )
        return {"success": True, "message": "Notification deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete notification: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/notifications/{notification_id}  (dynamic — must come AFTER static peers)
# ---------------------------------------------------------------------------

@router.get(
    "/notifications/{notification_id}", response_model=NotificationResponse
)
def get_notification(
    notification_id: str, current_user: dict = Depends(get_current_user)
):
    try:
        return _get_owned_or_403(notification_id, current_user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch notification: {e}",
        )
