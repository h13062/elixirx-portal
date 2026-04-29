"""Machine lifecycle router — status transitions, history, full detail.

Route ordering matters: static segments (/machines/status-summary,
/machines/bulk-status) MUST be registered before any /machines/{identifier}/...
route, and this router MUST be registered before inventory_router so its
static paths win against /machines/{machine_id} in inventory_router.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user, require_admin
from app.core.supabase_client import supabase_admin
from app.models.inventory_models import (
    BulkStatusResult,
    BulkStatusUpdate,
    MachineFullDetail,
    MachineIssueInfo,
    MachineResponse,
    MachineStatusLogEntry,
    MachineStatusSummary,
    MachineStatusUpdate,
    MachineStatusUpdateResponse,
    ProductResponse,
    ReservationInfo,
    WarrantyInfo,
)
from app.services.machine_lifecycle_service import MachineLifecycleService

router = APIRouter(prefix="/api", tags=["Machine Lifecycle"])
_lifecycle = MachineLifecycleService()


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _derive_machine_type(product_name: str | None) -> str | None:
    if not product_name:
        return None
    name = product_name.upper()
    if name.startswith("RX"):
        return "RX"
    if name.startswith("RO"):
        return "RO"
    return None


# ---------------------------------------------------------------------------
# Static routes — must come BEFORE any /machines/{identifier}/... route
# ---------------------------------------------------------------------------

# GET /api/machines/status-summary
@router.get("/machines/status-summary", response_model=MachineStatusSummary)
def status_summary(current_user: dict = Depends(get_current_user)):
    return _lifecycle.get_status_summary()


# POST /api/machines/bulk-status  (admin only)
@router.post("/machines/bulk-status", response_model=BulkStatusResult)
def bulk_status(
    payload: BulkStatusUpdate,
    current_user: dict = Depends(require_admin),
):
    return _lifecycle.bulk_update_status(payload, current_user["id"])


# ---------------------------------------------------------------------------
# Identifier-scoped routes — accept UUID or serial_number
# ---------------------------------------------------------------------------

# PUT /api/machines/{identifier}/status  (admin only)
@router.put(
    "/machines/{identifier}/status",
    response_model=MachineStatusUpdateResponse,
)
def update_machine_status(
    identifier: str,
    payload: MachineStatusUpdate,
    current_user: dict = Depends(require_admin),
):
    return _lifecycle.update_status(identifier, payload, current_user["id"])


# GET /api/machines/{identifier}/status-history
@router.get(
    "/machines/{identifier}/status-history",
    response_model=list[MachineStatusLogEntry],
)
def machine_status_history(
    identifier: str,
    current_user: dict = Depends(get_current_user),
):
    return _lifecycle.get_status_history(identifier)


# GET /api/machines/{identifier}/full-detail
# NOTE: Implemented inline (no repository, no service) — direct supabase_admin
# queries per spec. Best-effort lookups for warranty/reservations/issues so the
# endpoint works before those Sprint 3.2/3.3/3.4 tables exist.
@router.get(
    "/machines/{identifier}/full-detail",
    response_model=MachineFullDetail,
)
def machine_full_detail(
    identifier: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        # 1. Lookup machine by UUID or serial_number
        machine_query = (
            supabase_admin.table("machines").select("*, products(name, sku)")
        )
        if _is_uuid(identifier):
            machine_query = machine_query.eq("id", identifier)
        else:
            machine_query = machine_query.eq("serial_number", identifier)

        machine_result = machine_query.execute()
        if not machine_result.data:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Machine not found: {identifier}",
            )
        machine = machine_result.data[0]
        machine_id = machine["id"]

        # Build MachineResponse inline (derive machine_type from product name)
        product_join = machine.get("products") or {}
        product_name = (
            product_join.get("name") if isinstance(product_join, dict) else None
        )
        product_sku = (
            product_join.get("sku") if isinstance(product_join, dict) else None
        )
        machine_response = MachineResponse(
            id=machine["id"],
            serial_number=machine["serial_number"],
            product_id=machine["product_id"],
            product_name=product_name,
            product_sku=product_sku,
            machine_type=_derive_machine_type(product_name),
            batch_number=machine["batch_number"],
            manufacture_date=machine["manufacture_date"],
            status=machine["status"],
            reserved_by=machine.get("reserved_by"),
            reservation_expires_at=machine.get("reservation_expires_at"),
            registered_by=machine["registered_by"],
            created_at=machine["created_at"],
            updated_at=machine["updated_at"],
        )

        # 2. Product info
        product_response: ProductResponse | None = None
        product_result = (
            supabase_admin.table("products")
            .select("*")
            .eq("id", machine["product_id"])
            .execute()
        )
        if product_result.data:
            p = product_result.data[0]
            product_response = ProductResponse(
                id=p["id"],
                name=p["name"],
                category=p["category"],
                default_price=p.get("default_price", 0.0),
                sku=p.get("sku"),
                description=p.get("description"),
                is_serialized=p.get("is_serialized", False),
                is_active=p.get("is_active", True),
            )

        # 3. Status history (last 10)
        history_result = (
            supabase_admin.table("machine_status_log")
            .select("*, profiles(full_name)")
            .eq("machine_id", machine_id)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        history: list[MachineStatusLogEntry] = []
        for row in history_result.data or []:
            profile = row.get("profiles") or {}
            history.append(MachineStatusLogEntry(
                id=row["id"],
                from_status=row.get("from_status"),
                to_status=row["to_status"],
                changed_by=row.get("changed_by"),
                changed_by_name=(
                    profile.get("full_name") if isinstance(profile, dict) else None
                ),
                reason=row.get("reason"),
                created_at=row["created_at"],
            ))

        # 4. Warranty (best-effort — table may not exist yet)
        warranty: WarrantyInfo | None = None
        try:
            warranty_result = (
                supabase_admin.table("warranty")
                .select("*")
                .eq("machine_id", machine_id)
                .execute()
            )
            if warranty_result.data:
                w = warranty_result.data[0]
                warranty = WarrantyInfo(
                    start_date=w.get("start_date"),
                    end_date=w.get("end_date"),
                    status=w.get("status"),
                    duration_months=w.get("duration_months"),
                )
        except Exception:
            warranty = None

        # 5. Active reservation (best-effort)
        active_reservation: ReservationInfo | None = None
        try:
            res_result = (
                supabase_admin.table("reservations")
                .select("*, profiles(full_name)")
                .eq("machine_id", machine_id)
                .in_("status", ["pending", "approved"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if res_result.data:
                r = res_result.data[0]
                rep_profile = r.get("profiles") or {}
                active_reservation = ReservationInfo(
                    id=r["id"],
                    rep_id=r.get("rep_id"),
                    rep_name=(
                        rep_profile.get("full_name")
                        if isinstance(rep_profile, dict) else None
                    ),
                    status=r["status"],
                    created_at=r.get("created_at"),
                    expires_at=r.get("expires_at"),
                )
        except Exception:
            active_reservation = None

        # 6. Open issues (best-effort)
        open_issues: list[MachineIssueInfo] = []
        try:
            issues_result = (
                supabase_admin.table("machine_issues")
                .select("*, profiles(full_name)")
                .eq("machine_id", machine_id)
                .in_("status", ["open", "in_progress"])
                .order("created_at", desc=True)
                .execute()
            )
            for r in issues_result.data or []:
                open_issues.append(MachineIssueInfo(
                    id=r["id"],
                    title=r.get("title"),
                    status=r["status"],
                    created_at=r.get("created_at"),
                ))
        except Exception:
            open_issues = []

        return MachineFullDetail(
            machine=machine_response,
            product=product_response,
            status_history=history,
            warranty=warranty,
            active_reservation=active_reservation,
            open_issues=open_issues,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch machine detail: {e}",
        )


# ---------------------------------------------------------------------------
# DELETE /api/machines/{identifier}  (admin only) — Sprint 3 Task 3.6
# Hard delete. Refuses if the machine is sold/delivered, or if any
# warranty/reservation/issue references it. Cascades machine_status_log first
# so the machines.id FK doesn't block the delete.
# ---------------------------------------------------------------------------

BLOCKED_DELETE_STATUSES = ("sold", "delivered")


@router.delete("/machines/{identifier}")
def delete_machine(identifier: str, current_user: dict = Depends(require_admin)):
    try:
        # Lookup the machine
        q = supabase_admin.table("machines").select("id, serial_number, status")
        if _is_uuid(identifier):
            q = q.eq("id", identifier)
        else:
            q = q.eq("serial_number", identifier)
        result = q.execute()
        if not result.data:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Machine not found: {identifier}",
            )
        machine = result.data[0]
        machine_id = machine["id"]
        serial = machine["serial_number"]

        # Status guard
        if machine["status"] in BLOCKED_DELETE_STATUSES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot delete: machine is {machine['status']}. "
                    "Process a return first."
                ),
            )

        # Active warranty?
        warranty_check = (
            supabase_admin.table("warranty")
            .select("id")
            .eq("machine_id", machine_id)
            .execute()
        )
        if warranty_check.data:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete: machine has active warranty",
            )

        # Active reservation (pending or approved)?
        reservation_check = (
            supabase_admin.table("reservations")
            .select("id")
            .eq("machine_id", machine_id)
            .in_("status", ["pending", "approved"])
            .execute()
        )
        if reservation_check.data:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete: machine has active reservation",
            )

        # Open or in_progress issues?
        issues_check = (
            supabase_admin.table("machine_issues")
            .select("id")
            .eq("machine_id", machine_id)
            .in_("status", ["open", "in_progress"])
            .execute()
        )
        if issues_check.data:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete: machine has open issues",
            )

        # Cascade-delete log entries first to clear the FK
        supabase_admin.table("machine_status_log").delete().eq(
            "machine_id", machine_id
        ).execute()

        # Delete the machine
        supabase_admin.table("machines").delete().eq("id", machine_id).execute()

        return {"message": f"Machine {serial} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete machine: {e}",
        )
