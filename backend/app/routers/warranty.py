"""Warranty router (Sprint 3 Task 3.2).

Direct supabase_admin queries — no service/repository indirection per spec.
Status (active / expiring_soon / expired) is derived from end_date on every
read so the API always returns up-to-date status without a background job.

Route ordering: static segments (`/warranty/dashboard`,
`/warranty/check-expiring`, `/warranty/machine/...`, `/warranty/certificate/...`)
MUST be declared before `/warranty/{warranty_id}` so FastAPI doesn't capture
literals as the dynamic param.
"""

import io
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from fpdf import FPDF
from fpdf.enums import XPos, YPos

_NEXT_LINE = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}
_SAME_LINE = {"new_x": XPos.RIGHT, "new_y": YPos.TOP}

from app.core.auth import get_current_user, require_admin
from app.core.supabase_client import supabase_admin
from app.models.inventory_models import (
    ExpiringMachineInfo,
    WarrantyCreate,
    WarrantyDashboard,
    WarrantyExtendRequest,
    WarrantyResponse,
    WarrantyUpdate,
)

router = APIRouter(prefix="/api", tags=["Warranty"])

EXPIRING_WINDOW_DAYS = 30


# ---------------------------------------------------------------------------
# Helpers (inline — no repository pattern per spec)
# ---------------------------------------------------------------------------

def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def _add_months(d: date, months: int) -> date:
    """Add `months` to date `d`, clamping the day to the last valid day of the target month."""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    # Find the last day of the target month
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day_of_month = (next_month_first - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day_of_month))


def _derive_machine_type(product_name: str | None) -> str | None:
    if not product_name:
        return None
    name = product_name.upper()
    if name.startswith("RX"):
        return "RX"
    if name.startswith("RO"):
        return "RO"
    return None


def _calc_status(end_date: date) -> str:
    today = _today()
    if end_date < today:
        return "expired"
    if (end_date - today).days <= EXPIRING_WINDOW_DAYS:
        return "expiring_soon"
    return "active"


def _lookup_machine(identifier: str) -> dict | None:
    """Find a machine by UUID or serial_number, with product join."""
    q = supabase_admin.table("machines").select("*, products(name, sku)")
    if _is_uuid(identifier):
        q = q.eq("id", identifier)
    else:
        q = q.eq("serial_number", identifier)
    result = q.execute()
    return result.data[0] if result.data else None


def _build_warranty_response(row: dict) -> WarrantyResponse:
    """Hydrate a warranty row into a response, recomputing status from end_date."""
    end_date = _parse_date(row["end_date"])
    start_date = _parse_date(row["start_date"])
    original_end_date = (
        _parse_date(row["original_end_date"]) if row.get("original_end_date") else None
    )
    derived_status = _calc_status(end_date)

    machine_join = row.get("machines") or {}
    serial = machine_join.get("serial_number") if isinstance(machine_join, dict) else None
    batch_number = machine_join.get("batch_number") if isinstance(machine_join, dict) else None
    product_join = machine_join.get("products") if isinstance(machine_join, dict) else None
    product_name = product_join.get("name") if isinstance(product_join, dict) else None

    set_by_join = row.get("profiles") or {}
    set_by_name = set_by_join.get("full_name") if isinstance(set_by_join, dict) else None

    days_remaining = (end_date - _today()).days

    return WarrantyResponse(
        id=row["id"],
        machine_id=row["machine_id"],
        serial_number=serial,
        machine_type=_derive_machine_type(product_name),
        product_name=product_name,
        batch_number=batch_number,
        customer_name=row.get("customer_name"),
        customer_contact=row.get("customer_contact"),
        duration_months=row["duration_months"],
        start_date=start_date,
        end_date=end_date,
        status=derived_status,
        extended=bool(row.get("extended")),
        extension_reason=row.get("extension_reason"),
        original_end_date=original_end_date,
        set_by=row.get("set_by"),
        set_by_name=set_by_name,
        days_remaining=days_remaining,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


_WARRANTY_SELECT = (
    "*, machines(serial_number, batch_number, products(name, sku)), profiles(full_name)"
)


def _fetch_warranty_by_id(warranty_id: str) -> dict | None:
    r = (
        supabase_admin.table("warranty")
        .select(_WARRANTY_SELECT)
        .eq("id", warranty_id)
        .execute()
    )
    return r.data[0] if r.data else None


# ---------------------------------------------------------------------------
# POST /api/warranty  (admin only)
# ---------------------------------------------------------------------------

@router.post("/warranty", response_model=WarrantyResponse, status_code=201)
def create_warranty(payload: WarrantyCreate, current_user: dict = Depends(require_admin)):
    try:
        machine = _lookup_machine(payload.machine_id)
        if not machine:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Machine not found: {payload.machine_id}",
            )

        if machine["status"] != "delivered" and not payload.force:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Machine status is '{machine['status']}', not 'delivered'. "
                    "Pass force=true to create warranty anyway."
                ),
            )

        # No existing warranty for this machine
        existing = (
            supabase_admin.table("warranty")
            .select("id")
            .eq("machine_id", machine["id"])
            .execute()
        )
        if existing.data:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Warranty already exists for this machine",
            )

        start = payload.start_date or _today()
        duration = payload.duration_months or 12
        if duration <= 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="duration_months must be > 0",
            )
        end = _add_months(start, duration)

        now_iso = _now_iso()
        insert_data = {
            "machine_id": machine["id"],
            "customer_name": payload.customer_name,
            "customer_contact": payload.customer_contact,
            "duration_months": duration,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "status": _calc_status(end),
            "extended": False,
            "set_by": current_user["id"],
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        created = supabase_admin.table("warranty").insert(insert_data).execute()
        if not created.data:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create warranty",
            )

        full = _fetch_warranty_by_id(created.data[0]["id"])
        if not full:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Warranty created but could not be retrieved",
            )
        return _build_warranty_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create warranty: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/warranty
# ---------------------------------------------------------------------------

@router.get("/warranty", response_model=list[WarrantyResponse])
def list_warranties(
    status_filter: str | None = Query(default=None, alias="status"),
    machine_type: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    try:
        rows = (
            supabase_admin.table("warranty")
            .select(_WARRANTY_SELECT)
            .order("end_date", desc=False)
            .execute()
            .data
            or []
        )
        responses = [_build_warranty_response(r) for r in rows]

        if status_filter:
            responses = [r for r in responses if r.status == status_filter]

        if machine_type:
            prefix = machine_type.upper()
            responses = [
                r for r in responses
                if r.machine_type == prefix
            ]
        return responses
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch warranties: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/warranty/dashboard  (static — must come before /{warranty_id})
# ---------------------------------------------------------------------------

@router.get("/warranty/dashboard", response_model=WarrantyDashboard)
def warranty_dashboard(current_user: dict = Depends(get_current_user)):
    try:
        rows = (
            supabase_admin.table("warranty")
            .select(_WARRANTY_SELECT)
            .execute()
            .data
            or []
        )
        responses = [_build_warranty_response(r) for r in rows]

        active = sum(1 for r in responses if r.status == "active")
        expiring_soon = sum(1 for r in responses if r.status == "expiring_soon")
        expired = sum(1 for r in responses if r.status == "expired")

        expiring_machines = [
            ExpiringMachineInfo(
                warranty_id=r.id,
                machine_id=r.machine_id,
                serial_number=r.serial_number,
                customer_name=r.customer_name,
                end_date=r.end_date,
                days_remaining=r.days_remaining or 0,
            )
            for r in responses
            if r.status == "expiring_soon"
        ]
        expiring_machines.sort(key=lambda x: x.days_remaining)

        return WarrantyDashboard(
            active=active,
            expiring_soon=expiring_soon,
            expired=expired,
            total=len(responses),
            expiring_machines=expiring_machines,
        )
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch warranty dashboard: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/warranty/check-expiring  (static — must come before /{warranty_id})
# ---------------------------------------------------------------------------

@router.get("/warranty/check-expiring", response_model=list[ExpiringMachineInfo])
def check_expiring(current_user: dict = Depends(get_current_user)):
    try:
        rows = (
            supabase_admin.table("warranty")
            .select(_WARRANTY_SELECT)
            .execute()
            .data
            or []
        )
        responses = [_build_warranty_response(r) for r in rows]
        expiring = [r for r in responses if r.status == "expiring_soon"]

        # Best-effort: create a notification for each expiring warranty unless a
        # warranty_expiring notification was already created in the last 7 days.
        try:
            seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            for r in expiring:
                exists = (
                    supabase_admin.table("notifications")
                    .select("id")
                    .eq("type", "warranty_expiring")
                    .eq("machine_id", r.machine_id)
                    .gte("created_at", seven_days_ago)
                    .execute()
                )
                if exists.data:
                    continue
                supabase_admin.table("notifications").insert({
                    "type": "warranty_expiring",
                    "machine_id": r.machine_id,
                    "title": f"Warranty expiring for {r.serial_number}",
                    "message": (
                        f"Warranty for machine {r.serial_number or r.machine_id} "
                        f"expires on {r.end_date.isoformat()} "
                        f"({(r.days_remaining or 0)} days)."
                    ),
                    "read": False,
                    "created_at": _now_iso(),
                }).execute()
        except Exception:
            # Notifications schema may not match — don't fail the endpoint.
            pass

        return [
            ExpiringMachineInfo(
                warranty_id=r.id,
                machine_id=r.machine_id,
                serial_number=r.serial_number,
                customer_name=r.customer_name,
                end_date=r.end_date,
                days_remaining=r.days_remaining or 0,
            )
            for r in expiring
        ]
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch expiring warranties: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/warranty/machine/{identifier}  (static prefix — before /{warranty_id})
# ---------------------------------------------------------------------------

@router.get("/warranty/machine/{identifier}", response_model=WarrantyResponse)
def get_warranty_by_machine(
    identifier: str, current_user: dict = Depends(get_current_user)
):
    try:
        machine = _lookup_machine(identifier)
        if not machine:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"Machine not found: {identifier}"
            )
        rows = (
            supabase_admin.table("warranty")
            .select(_WARRANTY_SELECT)
            .eq("machine_id", machine["id"])
            .execute()
        )
        if not rows.data:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"No warranty exists for machine {identifier}",
            )
        return _build_warranty_response(rows.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch warranty: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/warranty/certificate/{machine_id}  (static prefix — before /{warranty_id})
# ---------------------------------------------------------------------------

@router.get("/warranty/certificate/{machine_id}")
def warranty_certificate(machine_id: str, current_user: dict = Depends(require_admin)):
    try:
        machine = _lookup_machine(machine_id)
        if not machine:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"Machine not found: {machine_id}"
            )
        rows = (
            supabase_admin.table("warranty")
            .select(_WARRANTY_SELECT)
            .eq("machine_id", machine["id"])
            .execute()
        )
        if not rows.data:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"No warranty exists for machine {machine_id}",
            )
        warranty = _build_warranty_response(rows.data[0])

        pdf_bytes = _render_certificate_pdf(warranty)
        filename = (
            f"warranty-{warranty.serial_number or warranty.machine_id}-"
            f"{warranty.id[:8]}.pdf"
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to render certificate: {e}",
        )


def _render_certificate_pdf(w: WarrantyResponse) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Brand header
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 12, "ElixirX", align="C", **_NEXT_LINE)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Core Pacific Inc. - ElixirX Division", align="C", **_NEXT_LINE)
    pdf.ln(8)

    # Title
    pdf.set_font("Helvetica", "B", 28)
    pdf.cell(0, 16, "Warranty Certificate", align="C", **_NEXT_LINE)
    pdf.ln(4)

    # Certificate number
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, f"Certificate No.: {w.id[:8].upper()}", align="C", **_NEXT_LINE)
    pdf.ln(8)

    # Machine details block
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Machine Details", **_NEXT_LINE)
    pdf.set_font("Helvetica", "", 11)
    _kv(pdf, "Serial Number", w.serial_number or w.machine_id)
    _kv(pdf, "Type", w.machine_type or "-")
    _kv(pdf, "Product", w.product_name or "-")
    _kv(pdf, "Batch", w.batch_number or "-")
    pdf.ln(4)

    # Customer block
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Customer", **_NEXT_LINE)
    pdf.set_font("Helvetica", "", 11)
    _kv(pdf, "Name", w.customer_name or "(not provided)")
    _kv(pdf, "Contact", w.customer_contact or "(not provided)")
    pdf.ln(4)

    # Coverage block
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Coverage", **_NEXT_LINE)
    pdf.set_font("Helvetica", "", 11)
    _kv(pdf, "Start Date", w.start_date.isoformat())
    _kv(pdf, "End Date", w.end_date.isoformat())
    _kv(pdf, "Duration", f"{w.duration_months} months")
    _kv(pdf, "Status", w.status.replace("_", " ").title())

    if w.extended:
        _kv(pdf, "Extended", "Yes")
        if w.original_end_date:
            _kv(pdf, "Original End Date", w.original_end_date.isoformat())
        if w.extension_reason:
            _kv(pdf, "Extension Reason", w.extension_reason)
    else:
        _kv(pdf, "Extended", "No")
    pdf.ln(6)

    # Signature
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Issued By", **_NEXT_LINE)
    pdf.set_font("Helvetica", "", 11)
    _kv(pdf, "Administrator", w.set_by_name or w.set_by or "(unknown)")
    _kv(pdf, "Issued At", w.created_at.strftime("%Y-%m-%d"))

    # Footer
    pdf.set_y(-25)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(
        0,
        5,
        "This certificate is valid only for the machine specified above.",
        align="C",
        **_NEXT_LINE,
    )
    pdf.cell(0, 5, "Core Pacific Inc. - ElixirX Division", align="C", **_NEXT_LINE)

    out = pdf.output()
    # fpdf2 returns bytearray; FPDF (legacy) may return str — normalize.
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)


def _kv(pdf: FPDF, label: str, value: str) -> None:
    pdf.cell(50, 7, f"{label}:", **_SAME_LINE)
    pdf.cell(0, 7, str(value), **_NEXT_LINE)


# ---------------------------------------------------------------------------
# PUT /api/warranty/{warranty_id}/extend  (admin only)
# Static-suffix dynamic — declare BEFORE plain /{warranty_id} PUT.
# ---------------------------------------------------------------------------

@router.put("/warranty/{warranty_id}/extend", response_model=WarrantyResponse)
def extend_warranty(
    warranty_id: str,
    payload: WarrantyExtendRequest,
    current_user: dict = Depends(require_admin),
):
    try:
        if payload.additional_months <= 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="additional_months must be > 0",
            )
        if not payload.reason or not payload.reason.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="reason is required",
            )

        existing = _fetch_warranty_by_id(warranty_id)
        if not existing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Warranty not found"
            )

        current_end = _parse_date(existing["end_date"])
        new_end = _add_months(current_end, payload.additional_months)
        new_duration = (existing.get("duration_months") or 0) + payload.additional_months

        update_data: dict = {
            "end_date": new_end.isoformat(),
            "extended": True,
            "extension_reason": payload.reason,
            "duration_months": new_duration,
            "status": _calc_status(new_end),
            "updated_at": _now_iso(),
        }
        # Save original_end_date once (first extension only)
        if not existing.get("original_end_date"):
            update_data["original_end_date"] = current_end.isoformat()

        supabase_admin.table("warranty").update(update_data).eq(
            "id", warranty_id
        ).execute()
        full = _fetch_warranty_by_id(warranty_id)
        return _build_warranty_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extend warranty: {e}",
        )


# ---------------------------------------------------------------------------
# PUT /api/warranty/{warranty_id}  (admin only)
# ---------------------------------------------------------------------------

@router.put("/warranty/{warranty_id}", response_model=WarrantyResponse)
def update_warranty(
    warranty_id: str,
    payload: WarrantyUpdate,
    current_user: dict = Depends(require_admin),
):
    try:
        existing = _fetch_warranty_by_id(warranty_id)
        if not existing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Warranty not found"
            )

        update_data = {
            k: v for k, v in payload.model_dump().items() if v is not None
        }
        if not update_data:
            return _build_warranty_response(existing)
        update_data["updated_at"] = _now_iso()

        supabase_admin.table("warranty").update(update_data).eq(
            "id", warranty_id
        ).execute()
        full = _fetch_warranty_by_id(warranty_id)
        return _build_warranty_response(full)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update warranty: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/warranty/{warranty_id}  (dynamic — must come AFTER static peers)
# ---------------------------------------------------------------------------

@router.get("/warranty/{warranty_id}", response_model=WarrantyResponse)
def get_warranty(warranty_id: str, current_user: dict = Depends(get_current_user)):
    try:
        row = _fetch_warranty_by_id(warranty_id)
        if not row:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Warranty not found"
            )
        return _build_warranty_response(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch warranty: {e}",
        )
