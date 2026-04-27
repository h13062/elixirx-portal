"""Machine lifecycle router — status transitions, history, full detail.

Route ordering matters: static segments (/machines/status-summary,
/machines/bulk-status) MUST be registered before any /machines/{identifier}/...
route, and this router MUST be registered before inventory_router so its
static paths win against /machines/{machine_id} in inventory_router.
"""

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user, require_admin
from app.models.inventory_models import (
    BulkStatusResult,
    BulkStatusUpdate,
    MachineFullDetail,
    MachineStatusLogEntry,
    MachineStatusSummary,
    MachineStatusUpdate,
    MachineStatusUpdateResponse,
)
from app.services.machine_lifecycle_service import MachineLifecycleService

router = APIRouter(prefix="/api", tags=["Machine Lifecycle"])
_lifecycle = MachineLifecycleService()


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
@router.get(
    "/machines/{identifier}/full-detail",
    response_model=MachineFullDetail,
)
def machine_full_detail(
    identifier: str,
    current_user: dict = Depends(get_current_user),
):
    return _lifecycle.get_full_detail(identifier)
