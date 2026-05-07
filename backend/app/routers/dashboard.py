"""Dashboard router (Sprint 4 Task 4.0).

Single GET /api/dashboard/summary endpoint that aggregates data from many
tables in one round trip:

- machines           — counts grouped by status
- warranties         — active / expiring_soon / expired / total
- issues             — counts by status + priority breakdown
- reservations       — counts by status (filtered to caller for reps)
- low_stock          — consumable products below their min_threshold
- recent_activity    — last 10 machine_status_log entries (with rep name)
- expiring_warranties— warranties expiring within 30 days

Direct supabase_admin queries — no service/repository indirection per spec.
Sub-section failures are handled best-effort: if one table is missing or
errors out, the affected section returns its zero/empty default and the rest
of the response still loads.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.supabase_client import supabase_admin
from app.models.dashboard_models import (
    DashboardIssueCounts,
    DashboardLowStock,
    DashboardMachineCounts,
    DashboardReservationCounts,
    DashboardSummaryResponse,
    DashboardWarrantyCounts,
    ExpiredWarrantyEntry,
    ExpiringWarrantyEntry,
    LowStockItem,
    RecentActivityEntry,
    RecentIssueEntry,
)

router = APIRouter(prefix="/api", tags=["Dashboard"])

EXPIRING_WINDOW_DAYS = 30
RECENT_ACTIVITY_LIMIT = 10
RECENT_ISSUES_LIMIT = 5

PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2, "low": 3}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _is_admin(profile: dict) -> bool:
    return profile.get("role") in ("admin", "super_admin")


# ---------------------------------------------------------------------------
# Per-section builders. Each is wrapped in try/except by the caller so a
# single failure doesn't break the whole response.
# ---------------------------------------------------------------------------

def _build_machines() -> DashboardMachineCounts:
    rows = (
        supabase_admin.table("machines").select("status").execute().data or []
    )
    counts = DashboardMachineCounts(total=len(rows))
    for r in rows:
        s = r.get("status")
        if hasattr(counts, s or ""):
            setattr(counts, s, getattr(counts, s) + 1)
    return counts


def _derive_machine_type(product_name: Optional[str]) -> Optional[str]:
    """Best-effort RX/RO derivation from a product name (matches warranty router)."""
    if not product_name:
        return None
    name = product_name.upper()
    if name.startswith("RX"):
        return "RX"
    if name.startswith("RO"):
        return "RO"
    return None


def _extract_serial_and_type(machine_join) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(machine_join, dict):
        return None, None
    serial = machine_join.get("serial_number")
    product = machine_join.get("products")
    product_name = product.get("name") if isinstance(product, dict) else None
    return serial, _derive_machine_type(product_name)


def _build_warranties() -> tuple[
    DashboardWarrantyCounts,
    list[ExpiringWarrantyEntry],
    list[ExpiredWarrantyEntry],
]:
    rows = (
        supabase_admin.table("warranty")
        .select(
            "id, machine_id, customer_name, end_date, duration_months, "
            "machines(serial_number, products(name))"
        )
        .execute()
        .data
        or []
    )
    today = _today()
    expiring: list[ExpiringWarrantyEntry] = []
    expired: list[ExpiredWarrantyEntry] = []
    counts = DashboardWarrantyCounts(total=len(rows))

    for r in rows:
        end_date = _parse_date(r.get("end_date"))
        if end_date is None:
            continue
        days_remaining = (end_date - today).days
        serial, machine_type = _extract_serial_and_type(r.get("machines"))
        duration_months = int(r.get("duration_months") or 0)

        if days_remaining < 0:
            counts.expired += 1
            expired.append(ExpiredWarrantyEntry(
                warranty_id=r["id"],
                machine_id=r["machine_id"],
                serial_number=serial,
                machine_type=machine_type,
                customer_name=r.get("customer_name"),
                end_date=end_date,
                days_overdue=abs(days_remaining),
            ))
        elif days_remaining <= EXPIRING_WINDOW_DAYS:
            counts.expiring_soon += 1
            expiring.append(ExpiringWarrantyEntry(
                warranty_id=r["id"],
                machine_id=r["machine_id"],
                serial_number=serial,
                machine_type=machine_type,
                customer_name=r.get("customer_name"),
                end_date=end_date,
                duration_months=duration_months,
                days_remaining=days_remaining,
            ))
        else:
            counts.active += 1

    # Soonest-expiring first; most-recently-expired first.
    expiring.sort(key=lambda x: x.days_remaining)
    expired.sort(key=lambda x: x.days_overdue)
    return counts, expiring, expired


def _build_issues(filter_user_id: Optional[str]) -> DashboardIssueCounts:
    q = supabase_admin.table("machine_issues").select("status, priority, reported_by")
    if filter_user_id:
        q = q.eq("reported_by", filter_user_id)
    rows = q.execute().data or []

    counts = DashboardIssueCounts(total=len(rows))
    for r in rows:
        s = r.get("status")
        p = r.get("priority")
        if hasattr(counts, s or ""):
            setattr(counts, s, getattr(counts, s) + 1)
        if p == "urgent":
            counts.urgent += 1
        elif p == "high":
            counts.high += 1
    return counts


def _build_recent_issues(filter_user_id: Optional[str]) -> list[RecentIssueEntry]:
    """Top N open/in_progress issues, sorted by priority then recency."""
    q = (
        supabase_admin.table("machine_issues")
        .select(
            "id, machine_id, title, priority, status, reported_by, "
            "created_at, machines(serial_number), "
            "reporter:profiles!reported_by(full_name)"
        )
        .in_("status", ["open", "in_progress"])
    )
    if filter_user_id:
        q = q.eq("reported_by", filter_user_id)
    rows = q.execute().data or []

    rows.sort(
        key=lambda r: (
            PRIORITY_RANK.get(r.get("priority"), 99),
            # newer-first within same priority
            -(_parse_iso_to_epoch(r.get("created_at")) or 0),
        )
    )
    out: list[RecentIssueEntry] = []
    for r in rows[:RECENT_ISSUES_LIMIT]:
        machine_join = r.get("machines") or {}
        serial = (
            machine_join.get("serial_number")
            if isinstance(machine_join, dict) else None
        )
        rep_join = r.get("reporter") or {}
        rep_name = (
            rep_join.get("full_name")
            if isinstance(rep_join, dict) else None
        )
        out.append(RecentIssueEntry(
            id=r["id"],
            machine_id=r["machine_id"],
            serial_number=serial,
            title=r["title"],
            priority=r["priority"],
            status=r["status"],
            reported_by=r.get("reported_by"),
            reported_by_name=rep_name,
            created_at=r["created_at"],
        ))
    return out


def _parse_iso_to_epoch(value) -> Optional[int]:
    """Best-effort ISO timestamp → epoch seconds for sorting; None on failure."""
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        return int(datetime.fromisoformat(s).timestamp())
    except (ValueError, TypeError):
        return None


def _build_reservations(filter_user_id: Optional[str]) -> DashboardReservationCounts:
    q = supabase_admin.table("reservations").select("status, reserved_by")
    if filter_user_id:
        q = q.eq("reserved_by", filter_user_id)
    rows = q.execute().data or []

    counts = DashboardReservationCounts(total=len(rows))
    for r in rows:
        s = r.get("status")
        if hasattr(counts, s or ""):
            setattr(counts, s, getattr(counts, s) + 1)
    return counts


def _build_low_stock() -> DashboardLowStock:
    """Items where min_threshold is set AND quantity < min_threshold."""
    rows = (
        supabase_admin.table("consumable_stock")
        .select("product_id, quantity, min_threshold, "
                "products(name, sku)")
        .execute()
        .data
        or []
    )
    items: list[LowStockItem] = []
    for r in rows:
        threshold = r.get("min_threshold")
        if threshold is None:
            continue
        qty = r.get("quantity") or 0
        if qty >= threshold:
            continue
        product_join = r.get("products") or {}
        name = (
            product_join.get("name") if isinstance(product_join, dict) else None
        ) or "(unknown)"
        sku = (
            product_join.get("sku") if isinstance(product_join, dict) else None
        )
        items.append(LowStockItem(
            product_id=r["product_id"],
            product_name=name,
            sku=sku,
            quantity=qty,
            min_threshold=threshold,
        ))
    items.sort(key=lambda x: (x.quantity - x.min_threshold))
    return DashboardLowStock(count=len(items), items=items)


def _build_recent_activity() -> list[RecentActivityEntry]:
    rows = (
        supabase_admin.table("machine_status_log")
        .select("id, machine_id, from_status, to_status, changed_by, "
                "reason, created_at, machines(serial_number), "
                "profiles(full_name)")
        .order("created_at", desc=True)
        .limit(RECENT_ACTIVITY_LIMIT)
        .execute()
        .data
        or []
    )
    out: list[RecentActivityEntry] = []
    for r in rows:
        machine_join = r.get("machines") or {}
        serial = (
            machine_join.get("serial_number")
            if isinstance(machine_join, dict) else None
        )
        prof_join = r.get("profiles") or {}
        full_name = (
            prof_join.get("full_name")
            if isinstance(prof_join, dict) else None
        )
        out.append(RecentActivityEntry(
            id=r["id"],
            machine_id=r["machine_id"],
            serial_number=serial,
            from_status=r.get("from_status"),
            to_status=r["to_status"],
            changed_by=r.get("changed_by"),
            changed_by_name=full_name,
            reason=r.get("reason"),
            created_at=r["created_at"],
        ))
    return out


# ---------------------------------------------------------------------------
# GET /api/dashboard/summary
# ---------------------------------------------------------------------------

@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(current_user: dict = Depends(get_current_user)):
    """Single round-trip aggregate for the dashboard page.

    Reps get reservations + issues filtered to their own user_id; everything
    else is global. Each section is built best-effort: a missing table or a
    join failure returns the empty/zero default for that section but does not
    fail the whole response.
    """
    rep_filter_id: Optional[str] = (
        None if _is_admin(current_user) else current_user["id"]
    )

    try:
        try:
            machines = _build_machines()
        except Exception:
            machines = DashboardMachineCounts()

        try:
            warranties, expiring_warranties, expired_warranties = _build_warranties()
        except Exception:
            warranties = DashboardWarrantyCounts()
            expiring_warranties = []
            expired_warranties = []

        try:
            issues = _build_issues(rep_filter_id)
        except Exception:
            issues = DashboardIssueCounts()

        try:
            recent_issues = _build_recent_issues(rep_filter_id)
        except Exception:
            recent_issues = []

        try:
            reservations = _build_reservations(rep_filter_id)
        except Exception:
            reservations = DashboardReservationCounts()

        try:
            low_stock = _build_low_stock()
        except Exception:
            low_stock = DashboardLowStock(count=0, items=[])

        try:
            recent_activity = _build_recent_activity()
        except Exception:
            recent_activity = []

        return DashboardSummaryResponse(
            machines=machines,
            warranties=warranties,
            issues=issues,
            reservations=reservations,
            low_stock=low_stock,
            recent_activity=recent_activity,
            recent_issues=recent_issues,
            expiring_warranties=expiring_warranties,
            expired_warranties=expired_warranties,
        )
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build dashboard summary: {e}",
        )
