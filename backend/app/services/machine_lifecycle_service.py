"""Machine lifecycle service — status transitions, history, full machine detail.

Every status change writes an entry to machine_status_log. The valid transition
graph below enforces the operational state machine; admins can override with
force=True (still logged, prefixed with FORCED).
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status

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
from app.repositories.machine_repository import MachineRepository
from app.repositories.machine_status_log_repository import (
    MachineStatusLogRepository,
)
from app.repositories.product_repository import ProductRepository
from app.services.inventory_service import InventoryService


# Valid forward transitions. Reverse/manual moves require force=True.
VALID_TRANSITIONS: dict[str, list[str]] = {
    "available": ["reserved"],
    "reserved": ["available", "ordered"],
    "ordered": ["sold", "available"],
    "sold": ["delivered", "available"],
    "delivered": ["returned"],
    "returned": ["available"],
}

VALID_STATUSES: set[str] = {
    "available", "reserved", "ordered", "sold", "delivered", "returned",
}


class MachineLifecycleService:
    """Business logic for machine status transitions and machine detail views."""

    def __init__(self) -> None:
        self._machines = MachineRepository(supabase_admin)
        self._products = ProductRepository(supabase_admin)
        self._log = MachineStatusLogRepository(supabase_admin)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _resolve_machine_or_404(self, identifier: str) -> dict:
        row = self._machines.find_by_identifier(identifier)
        if not row:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Machine not found: {identifier}",
            )
        return row

    @staticmethod
    def _validate_status(value: str) -> None:
        if value not in VALID_STATUSES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid status '{value}'. "
                    f"Allowed: {sorted(VALID_STATUSES)}"
                ),
            )

    @staticmethod
    def _check_transition(current: str, new: str, force: bool) -> None:
        if current == new:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Machine is already in status '{current}'",
            )
        if force:
            return
        allowed = VALID_TRANSITIONS.get(current, [])
        if new not in allowed:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid transition from '{current}' to '{new}'. "
                    f"Allowed: {allowed}. Use force=true to override."
                ),
            )

    # -------------------------------------------------------------------------
    # PUT /api/machines/{identifier}/status
    # -------------------------------------------------------------------------

    def update_status(
        self,
        identifier: str,
        payload: MachineStatusUpdate,
        actor_id: str,
    ) -> MachineStatusUpdateResponse:
        try:
            self._validate_status(payload.new_status)

            machine = self._resolve_machine_or_404(identifier)
            current_status = machine["status"]
            force = bool(payload.force)

            self._check_transition(current_status, payload.new_status, force)

            log_reason = payload.reason
            if force:
                log_reason = f"FORCED: {payload.reason or 'no reason provided'}"

            now_iso = self._now_iso()
            self._machines.update_status(machine["id"], payload.new_status, now_iso)
            self._log.create({
                "machine_id": machine["id"],
                "from_status": current_status,
                "to_status": payload.new_status,
                "changed_by": actor_id,
                "reason": log_reason,
                "created_at": now_iso,
            })

            updated = self._machines.find_by_id(machine["id"])
            if not updated:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Status updated but machine could not be retrieved",
                )

            return MachineStatusUpdateResponse(
                machine=InventoryService._build_machine_response(updated),
                warranty_setup_required=(payload.new_status == "delivered"),
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update machine status: {e}",
            )

    # -------------------------------------------------------------------------
    # GET /api/machines/{identifier}/status-history
    # -------------------------------------------------------------------------

    def get_status_history(self, identifier: str) -> list[MachineStatusLogEntry]:
        try:
            machine = self._resolve_machine_or_404(identifier)
            rows = self._log.list_for_machine(machine["id"])
            return [self._build_log_entry(r) for r in rows]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch status history: {e}",
            )

    @staticmethod
    def _build_log_entry(row: dict) -> MachineStatusLogEntry:
        profile = row.get("profiles") or {}
        changed_by_name = profile.get("name") if isinstance(profile, dict) else None
        return MachineStatusLogEntry(
            id=row["id"],
            from_status=row.get("from_status"),
            to_status=row["to_status"],
            changed_by=row.get("changed_by"),
            changed_by_name=changed_by_name,
            reason=row.get("reason"),
            created_at=row["created_at"],
        )

    # -------------------------------------------------------------------------
    # GET /api/machines/{identifier}/full-detail
    # -------------------------------------------------------------------------

    def get_full_detail(self, identifier: str) -> MachineFullDetail:
        try:
            machine = self._resolve_machine_or_404(identifier)

            machine_response = InventoryService._build_machine_response(machine)

            product_response: ProductResponse | None = None
            product_row = self._products.find_by_id(machine["product_id"])
            if product_row:
                product_response = ProductResponse(
                    id=product_row["id"],
                    name=product_row["name"],
                    category=product_row["category"],
                    default_price=product_row.get("default_price", 0.0),
                    sku=product_row.get("sku"),
                    description=product_row.get("description"),
                    is_serialized=product_row.get("is_serialized", False),
                    is_active=product_row.get("is_active", True),
                )

            history_rows = self._log.list_for_machine(machine["id"], limit=10)
            history = [self._build_log_entry(r) for r in history_rows]

            return MachineFullDetail(
                machine=machine_response,
                product=product_response,
                status_history=history,
                warranty=self._fetch_warranty(machine["id"]),
                active_reservation=self._fetch_active_reservation(machine["id"]),
                open_issues=self._fetch_open_issues(machine["id"]),
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch machine detail: {e}",
            )

    def _fetch_warranty(self, machine_id: str) -> WarrantyInfo | None:
        """Best-effort warranty lookup. Returns None if table doesn't exist yet."""
        try:
            result = (
                supabase_admin.table("warranty")
                .select("start_date, end_date, status, duration_months")
                .eq("machine_id", machine_id)
                .execute()
            )
            if not result.data:
                return None
            row = result.data[0]
            return WarrantyInfo(
                start_date=row.get("start_date"),
                end_date=row.get("end_date"),
                status=row.get("status"),
                duration_months=row.get("duration_months"),
            )
        except Exception:
            return None

    def _fetch_active_reservation(self, machine_id: str) -> ReservationInfo | None:
        """Best-effort reservation lookup. Returns None if table doesn't exist yet."""
        try:
            result = (
                supabase_admin.table("reservations")
                .select(
                    "id, rep_id, status, created_at, expires_at, profiles:rep_id(name)"
                )
                .eq("machine_id", machine_id)
                .in_("status", ["pending", "approved"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if not result.data:
                return None
            row = result.data[0]
            profile = row.get("profiles") or {}
            return ReservationInfo(
                id=row["id"],
                rep_id=row.get("rep_id"),
                rep_name=profile.get("name") if isinstance(profile, dict) else None,
                status=row["status"],
                created_at=row.get("created_at"),
                expires_at=row.get("expires_at"),
            )
        except Exception:
            return None

    def _fetch_open_issues(self, machine_id: str) -> list[MachineIssueInfo]:
        """Best-effort issue lookup. Returns [] if table doesn't exist yet."""
        try:
            result = (
                supabase_admin.table("machine_issues")
                .select("id, title, status, created_at")
                .eq("machine_id", machine_id)
                .in_("status", ["open", "in_progress"])
                .order("created_at", desc=True)
                .execute()
            )
            return [
                MachineIssueInfo(
                    id=r["id"],
                    title=r.get("title"),
                    status=r["status"],
                    created_at=r.get("created_at"),
                )
                for r in (result.data or [])
            ]
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # POST /api/machines/bulk-status
    # -------------------------------------------------------------------------

    def bulk_update_status(
        self,
        payload: BulkStatusUpdate,
        actor_id: str,
    ) -> BulkStatusResult:
        try:
            self._validate_status(payload.new_status)
            if not payload.machine_ids:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="machine_ids must not be empty",
                )

            updated = 0
            failed = 0
            errors: list[str] = []

            single_payload = MachineStatusUpdate(
                new_status=payload.new_status,
                reason=payload.reason,
                force=payload.force,
            )

            for identifier in payload.machine_ids:
                try:
                    self.update_status(identifier, single_payload, actor_id)
                    updated += 1
                except HTTPException as he:
                    failed += 1
                    errors.append(f"{identifier}: {he.detail}")
                except Exception as e:
                    failed += 1
                    errors.append(f"{identifier}: {e}")

            return BulkStatusResult(updated=updated, failed=failed, errors=errors)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to bulk update status: {e}",
            )

    # -------------------------------------------------------------------------
    # GET /api/machines/status-summary
    # -------------------------------------------------------------------------

    def get_status_summary(self) -> MachineStatusSummary:
        try:
            counts = self._machines.count_by_status()
            return MachineStatusSummary(
                available=counts.get("available", 0),
                reserved=counts.get("reserved", 0),
                ordered=counts.get("ordered", 0),
                sold=counts.get("sold", 0),
                delivered=counts.get("delivered", 0),
                returned=counts.get("returned", 0),
                total=sum(counts.values()),
            )
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch status summary: {e}",
            )
