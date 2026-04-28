"""Reservations router (Sprint 3 Task 3.3).

Direct supabase_admin queries — no service/repository per spec.

Lifecycle:
- Rep creates reservation (status=pending, machine stays available).
- Admin approves → reservation.expires_at = now + 7d, machine → reserved,
  machines.reserved_by + reservation_expires_at populated, log entry written.
- Admin denies → reservation status=denied, machine unchanged.
- Owner/admin cancels → if was approved, machine returns to available.
- check-expired → for every approved reservation past its expires_at, mark
  expired and release the machine.

Notifications writes are best-effort: wrapped in try/except so schema variance
doesn't break the main flow.

Route ordering: static segments (`/reservations/expiring-soon`,
`/reservations/check-expired`, `/reservations/machine/...`) MUST be declared
before `/reservations/{reservation_id}` so FastAPI doesn't capture literals
as the dynamic param.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user, require_admin
from app.core.helpers import is_uuid, lookup_machine
from app.core.supabase_client import supabase_admin
from app.models.inventory_models import (
    ExpiredReservationsResult,
    ExpiringSoonReservation,
    ReservationCreate,
    ReservationDenyRequest,
    ReservationResponse,
)

router = APIRouter(prefix="/api", tags=["Reservations"])

RESERVATION_DURATION_DAYS = 7
EXPIRING_SOON_HOURS = 24

ACTIVE_STATUSES = ("pending", "approved")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_dt().isoformat()


def _is_admin(profile: dict) -> bool:
    return profile.get("role") in ("admin", "super_admin")


_RESERVATION_SELECT = (
    "*, machines(serial_number, products(name)), "
    "reserved_by_profile:profiles!reserved_by(full_name), "
    "approved_by_profile:profiles!approved_by(full_name)"
)


def _fetch_reservation_by_id(reservation_id: str) -> dict | None:
    r = (
        supabase_admin.table("reservations")
        .select(_RESERVATION_SELECT)
        .eq("id", reservation_id)
        .execute()
    )
    return r.data[0] if r.data else None


def _build_reservation_response(row: dict) -> ReservationResponse:
    machine_join = row.get("machines") or {}
    serial = machine_join.get("serial_number") if isinstance(machine_join, dict) else None
    product_join = machine_join.get("products") if isinstance(machine_join, dict) else None
    product_name = product_join.get("name") if isinstance(product_join, dict) else None

    reserved_profile = row.get("reserved_by_profile") or {}
    reserved_by_name = (
        reserved_profile.get("full_name")
        if isinstance(reserved_profile, dict) else None
    )

    approved_profile = row.get("approved_by_profile") or {}
    approved_by_name = (
        approved_profile.get("full_name")
        if isinstance(approved_profile, dict) else None
    )

    return ReservationResponse(
        id=row["id"],
        machine_id=row["machine_id"],
        serial_number=serial,
        product_name=product_name,
        reserved_by=row.get("reserved_by"),
        reserved_by_name=reserved_by_name,
        reserved_for=row.get("reserved_for"),
        status=row["status"],
        approved_by=row.get("approved_by"),
        approved_by_name=approved_by_name,
        deny_reason=row.get("deny_reason"),
        expires_at=row.get("expires_at"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _has_active_reservation(machine_id: str) -> bool:
    r = (
        supabase_admin.table("reservations")
        .select("id")
        .eq("machine_id", machine_id)
        .in_("status", list(ACTIVE_STATUSES))
        .execute()
    )
    return bool(r.data)


def _log_status_change(
    machine_id: str,
    from_status: str,
    to_status: str,
    changed_by: str,
    reason: str,
) -> None:
    """Write an entry to machine_status_log. Failure raises so the caller can decide."""
    supabase_admin.table("machine_status_log").insert({
        "machine_id": machine_id,
        "from_status": from_status,
        "to_status": to_status,
        "changed_by": changed_by,
        "reason": reason,
        "created_at": _now_iso(),
    }).execute()


def _set_machine_reserved(
    machine: dict,
    reserved_by_user: str,
    expires_at: datetime,
    changed_by: str,
    reason: str,
) -> None:
    now_iso = _now_iso()
    supabase_admin.table("machines").update({
        "status": "reserved",
        "reserved_by": reserved_by_user,
        "reservation_expires_at": expires_at.isoformat(),
        "updated_at": now_iso,
    }).eq("id", machine["id"]).execute()
    _log_status_change(
        machine["id"], machine["status"], "reserved", changed_by, reason
    )


def _release_machine(machine_id: str, current_status: str, changed_by: str, reason: str) -> None:
    """Set machine back to available, clear reservation fields, log the change."""
    supabase_admin.table("machines").update({
        "status": "available",
        "reserved_by": None,
        "reservation_expires_at": None,
        "updated_at": _now_iso(),
    }).eq("id", machine_id).execute()
    _log_status_change(machine_id, current_status, "available", changed_by, reason)


def _notify(payload: dict) -> None:
    """Best-effort notification insert. Schema may vary; failures are swallowed."""
    try:
        supabase_admin.table("notifications").insert({
            "read": False,
            "created_at": _now_iso(),
            **payload,
        }).execute()
    except Exception:
        pass


def _notify_admins(payload: dict) -> None:
    """Send `payload` (sans user_id) to every admin/super_admin profile."""
    try:
        admins = (
            supabase_admin.table("profiles")
            .select("id")
            .in_("role", ["admin", "super_admin"])
            .execute()
            .data
            or []
        )
        for a in admins:
            _notify({**payload, "user_id": a["id"]})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# POST /api/reservations  (any authenticated user)
# ---------------------------------------------------------------------------

@router.post("/reservations", response_model=ReservationResponse, status_code=201)
def create_reservation(
    payload: ReservationCreate,
    current_user: dict = Depends(get_current_user),
):
    try:
        if not payload.reserved_for or not payload.reserved_for.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="reserved_for is required",
            )

        machine = lookup_machine(payload.machine_id)
        if not machine:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Machine not found: {payload.machine_id}",
            )

        if machine["status"] != "available":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Machine is not available, current status: {machine['status']}",
            )

        if _has_active_reservation(machine["id"]):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Machine already has an active reservation",
            )

        now_iso = _now_iso()
        created = (
            supabase_admin.table("reservations").insert({
                "machine_id": machine["id"],
                "reserved_by": current_user["id"],
                "reserved_for": payload.reserved_for,
                "status": "pending",
                "expires_at": None,
                "created_at": now_iso,
                "updated_at": now_iso,
            }).execute()
        )
        if not created.data:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create reservation",
            )
        reservation_id = created.data[0]["id"]

        # Notify all admins
        product_join = machine.get("products") or {}
        serial = machine["serial_number"]
        rep_name = current_user.get("full_name") or current_user.get("email") or "Rep"
        _notify_admins({
            "type": "reservation_request",
            "title": "Reservation Request",
            "message": (
                f"{rep_name} requested reservation for machine {serial} "
                f"for {payload.reserved_for}"
            ),
            "entity_type": "reservation",
            "entity_id": reservation_id,
            "machine_id": machine["id"],
        })

        full = _fetch_reservation_by_id(reservation_id)
        if not full:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Reservation created but could not be retrieved",
            )
        return _build_reservation_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create reservation: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/reservations
# ---------------------------------------------------------------------------

@router.get("/reservations", response_model=list[ReservationResponse])
def list_reservations(
    status_filter: str | None = Query(default=None, alias="status"),
    machine_id: str | None = Query(default=None),
    rep_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    try:
        q = (
            supabase_admin.table("reservations")
            .select(_RESERVATION_SELECT)
            .order("created_at", desc=True)
        )
        if status_filter:
            q = q.eq("status", status_filter)
        if rep_id:
            q = q.eq("reserved_by", rep_id)
        if machine_id:
            machine = lookup_machine(machine_id)
            if not machine:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail=f"Machine not found: {machine_id}",
                )
            q = q.eq("machine_id", machine["id"])
        rows = q.execute().data or []
        return [_build_reservation_response(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch reservations: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/reservations/expiring-soon  (static — must come before /{id})
# ---------------------------------------------------------------------------

@router.get(
    "/reservations/expiring-soon",
    response_model=list[ExpiringSoonReservation],
)
def expiring_soon(current_user: dict = Depends(get_current_user)):
    try:
        cutoff = (_now_dt() + timedelta(hours=EXPIRING_SOON_HOURS)).isoformat()
        rows = (
            supabase_admin.table("reservations")
            .select(_RESERVATION_SELECT)
            .eq("status", "approved")
            .lt("expires_at", cutoff)
            .order("expires_at", desc=False)
            .execute()
            .data
            or []
        )
        result: list[ExpiringSoonReservation] = []
        now = _now_dt()
        for r in rows:
            if not r.get("expires_at"):
                continue
            expires = datetime.fromisoformat(str(r["expires_at"]).replace("Z", "+00:00"))
            hours = max(0, int((expires - now).total_seconds() // 3600))
            machine_join = r.get("machines") or {}
            serial = (
                machine_join.get("serial_number") if isinstance(machine_join, dict) else None
            )
            rep_profile = r.get("reserved_by_profile") or {}
            rep_name = (
                rep_profile.get("full_name") if isinstance(rep_profile, dict) else None
            )
            result.append(ExpiringSoonReservation(
                reservation_id=r["id"],
                machine_id=r["machine_id"],
                serial_number=serial,
                reserved_by=r.get("reserved_by"),
                rep_name=rep_name,
                reserved_for=r.get("reserved_for"),
                expires_at=expires,
                hours_remaining=hours,
            ))
        return result
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch expiring reservations: {e}",
        )


# ---------------------------------------------------------------------------
# POST /api/reservations/check-expired  (admin only) — static, before /{id}
# ---------------------------------------------------------------------------

@router.post(
    "/reservations/check-expired",
    response_model=ExpiredReservationsResult,
)
def check_expired(current_user: dict = Depends(require_admin)):
    try:
        now_iso = _now_iso()
        candidates = (
            supabase_admin.table("reservations")
            .select(_RESERVATION_SELECT)
            .eq("status", "approved")
            .lt("expires_at", now_iso)
            .execute()
            .data
            or []
        )

        expired_responses: list[ReservationResponse] = []
        for res in candidates:
            try:
                # Mark reservation expired
                supabase_admin.table("reservations").update({
                    "status": "expired",
                    "updated_at": _now_iso(),
                }).eq("id", res["id"]).execute()

                # Release the machine if it's currently reserved
                machine_row = (
                    supabase_admin.table("machines")
                    .select("id, status")
                    .eq("id", res["machine_id"])
                    .execute()
                    .data
                )
                if machine_row and machine_row[0]["status"] == "reserved":
                    _release_machine(
                        res["machine_id"],
                        machine_row[0]["status"],
                        current_user["id"],
                        "Reservation expired",
                    )

                # Notify the rep
                machine_join = res.get("machines") or {}
                serial = (
                    machine_join.get("serial_number")
                    if isinstance(machine_join, dict) else None
                )
                _notify({
                    "user_id": res.get("reserved_by"),
                    "type": "reservation_expiring",
                    "title": "Reservation Expired",
                    "message": (
                        f"Your reservation for machine {serial or res['machine_id']} "
                        "has expired."
                    ),
                    "entity_type": "reservation",
                    "entity_id": res["id"],
                    "machine_id": res["machine_id"],
                })

                refreshed = _fetch_reservation_by_id(res["id"])
                if refreshed:
                    expired_responses.append(_build_reservation_response(refreshed))
            except Exception:
                # Skip individual failures so one bad row doesn't kill the batch
                continue

        return ExpiredReservationsResult(
            expired_count=len(expired_responses),
            expired_reservations=expired_responses,
        )
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check expired reservations: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/reservations/machine/{identifier}  (3-segment, static prefix)
# ---------------------------------------------------------------------------

@router.get(
    "/reservations/machine/{identifier}",
    response_model=ReservationResponse,
)
def get_active_reservation_for_machine(
    identifier: str, current_user: dict = Depends(get_current_user)
):
    try:
        machine = lookup_machine(identifier)
        if not machine:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Machine not found: {identifier}",
            )
        rows = (
            supabase_admin.table("reservations")
            .select(_RESERVATION_SELECT)
            .eq("machine_id", machine["id"])
            .in_("status", list(ACTIVE_STATUSES))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not rows.data:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"No active reservation for machine {identifier}",
            )
        return _build_reservation_response(rows.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch reservation: {e}",
        )


# ---------------------------------------------------------------------------
# PUT /api/reservations/{id}/approve  (admin only) — 3-seg, declare BEFORE /{id}
# ---------------------------------------------------------------------------

@router.put(
    "/reservations/{reservation_id}/approve",
    response_model=ReservationResponse,
)
def approve_reservation(
    reservation_id: str, current_user: dict = Depends(require_admin)
):
    try:
        res = _fetch_reservation_by_id(reservation_id)
        if not res:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Reservation not found"
            )
        if res["status"] != "pending":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot approve reservation in status '{res['status']}'",
            )

        machine_rows = (
            supabase_admin.table("machines")
            .select("id, status, serial_number")
            .eq("id", res["machine_id"])
            .execute()
            .data
        )
        if not machine_rows:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Machine for this reservation no longer exists",
            )
        machine = machine_rows[0]

        expires_at = _now_dt() + timedelta(days=RESERVATION_DURATION_DAYS)
        now_iso = _now_iso()

        # Update reservation
        supabase_admin.table("reservations").update({
            "status": "approved",
            "approved_by": current_user["id"],
            "expires_at": expires_at.isoformat(),
            "updated_at": now_iso,
        }).eq("id", reservation_id).execute()

        # Update machine + log status change
        _set_machine_reserved(
            machine,
            reserved_by_user=res["reserved_by"],
            expires_at=expires_at,
            changed_by=current_user["id"],
            reason=f"Reservation approved: {res.get('reserved_for') or '-'}",
        )

        # Notify the rep
        _notify({
            "user_id": res.get("reserved_by"),
            "type": "reservation_approved",
            "title": "Reservation Approved",
            "message": (
                f"Your reservation for machine {machine['serial_number']} has been "
                f"approved. Expires on {expires_at.date().isoformat()}."
            ),
            "entity_type": "reservation",
            "entity_id": reservation_id,
            "machine_id": machine["id"],
        })

        full = _fetch_reservation_by_id(reservation_id)
        return _build_reservation_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve reservation: {e}",
        )


# ---------------------------------------------------------------------------
# PUT /api/reservations/{id}/deny  (admin only)
# ---------------------------------------------------------------------------

@router.put(
    "/reservations/{reservation_id}/deny",
    response_model=ReservationResponse,
)
def deny_reservation(
    reservation_id: str,
    payload: ReservationDenyRequest,
    current_user: dict = Depends(require_admin),
):
    try:
        if not payload.reason or not payload.reason.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="reason is required"
            )

        res = _fetch_reservation_by_id(reservation_id)
        if not res:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Reservation not found"
            )
        if res["status"] != "pending":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot deny reservation in status '{res['status']}'",
            )

        supabase_admin.table("reservations").update({
            "status": "denied",
            "deny_reason": payload.reason,
            "approved_by": current_user["id"],
            "updated_at": _now_iso(),
        }).eq("id", reservation_id).execute()

        # Notify the rep
        machine_join = res.get("machines") or {}
        serial = (
            machine_join.get("serial_number") if isinstance(machine_join, dict) else None
        )
        _notify({
            "user_id": res.get("reserved_by"),
            "type": "reservation_denied",
            "title": "Reservation Denied",
            "message": (
                f"Your reservation for machine {serial or res['machine_id']} "
                f"was denied. Reason: {payload.reason}"
            ),
            "entity_type": "reservation",
            "entity_id": reservation_id,
            "machine_id": res["machine_id"],
        })

        full = _fetch_reservation_by_id(reservation_id)
        return _build_reservation_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deny reservation: {e}",
        )


# ---------------------------------------------------------------------------
# PUT /api/reservations/{id}/cancel  (owner or admin)
# ---------------------------------------------------------------------------

@router.put(
    "/reservations/{reservation_id}/cancel",
    response_model=ReservationResponse,
)
def cancel_reservation(
    reservation_id: str, current_user: dict = Depends(get_current_user)
):
    try:
        res = _fetch_reservation_by_id(reservation_id)
        if not res:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Reservation not found"
            )

        # Authorization: owner or admin
        if res["reserved_by"] != current_user["id"] and not _is_admin(current_user):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Only the reservation owner or an admin can cancel",
            )

        if res["status"] not in ("pending", "approved"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel reservation in status '{res['status']}'",
            )

        was_approved = res["status"] == "approved"

        # Update reservation
        supabase_admin.table("reservations").update({
            "status": "cancelled",
            "updated_at": _now_iso(),
        }).eq("id", reservation_id).execute()

        # Release machine if it was reserved by this approval
        if was_approved:
            machine_rows = (
                supabase_admin.table("machines")
                .select("id, status")
                .eq("id", res["machine_id"])
                .execute()
                .data
            )
            if machine_rows and machine_rows[0]["status"] == "reserved":
                _release_machine(
                    res["machine_id"],
                    machine_rows[0]["status"],
                    current_user["id"],
                    "Reservation cancelled",
                )

        full = _fetch_reservation_by_id(reservation_id)
        return _build_reservation_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel reservation: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/reservations/{id}  (dynamic — must come AFTER static peers)
# ---------------------------------------------------------------------------

@router.get(
    "/reservations/{reservation_id}",
    response_model=ReservationResponse,
)
def get_reservation(
    reservation_id: str, current_user: dict = Depends(get_current_user)
):
    try:
        row = _fetch_reservation_by_id(reservation_id)
        if not row:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Reservation not found"
            )
        return _build_reservation_response(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch reservation: {e}",
        )
