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

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user
from app.core.supabase_client import supabase_admin
from app.models.dashboard_models import (
    ActivityFeedEntry,
    DashboardIssueCounts,
    DashboardLowStock,
    DashboardMachineCounts,
    DashboardReservationCounts,
    DashboardSummaryResponse,
    DashboardWarrantyCounts,
    ExpiredWarrantyEntry,
    ExpiringWarrantyEntry,
    LowStockItem,
    MyReservationEntry,
    RecentActivityEntry,
    RecentIssueEntry,
    ReportDateRange,
    ReportIssues,
    ReportMachines,
    ReportReservations,
    ReportStock,
    ReportTopRep,
    ReportWarranties,
    SummaryReportResponse,
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
            "created_at, machines(serial_number, products(name)), "
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
        if isinstance(machine_join, dict):
            serial = machine_join.get("serial_number")
            product = machine_join.get("products")
            product_name = (
                product.get("name") if isinstance(product, dict) else None
            )
        else:
            serial = None
            product_name = None
        machine_type = _derive_machine_type(product_name) or \
            _derive_machine_type_from_serial(serial)
        rep_join = r.get("reporter") or {}
        rep_name = (
            rep_join.get("full_name")
            if isinstance(rep_join, dict) else None
        )
        out.append(RecentIssueEntry(
            id=r["id"],
            machine_id=r["machine_id"],
            serial_number=serial,
            machine_serial=serial,
            machine_type=machine_type,
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
    return DashboardLowStock(
        count=len(items),
        total_tracked=len(rows),
        items=items,
    )


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


def _build_my_reservations(user_id: str) -> list[MyReservationEntry]:
    """Last 5 reservations created by the given rep (Task 4.7)."""
    rows = (
        supabase_admin.table("reservations")
        .select(
            "id, machine_id, status, expires_at, created_at, "
            "machines(serial_number, products(name))"
        )
        .eq("reserved_by", user_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
        .data
        or []
    )
    out: list[MyReservationEntry] = []
    for r in rows:
        machine_join = r.get("machines") or {}
        if isinstance(machine_join, dict):
            serial = machine_join.get("serial_number")
            product = machine_join.get("products")
            product_name = (
                product.get("name") if isinstance(product, dict) else None
            )
        else:
            serial = None
            product_name = None
        machine_type = _derive_machine_type(product_name) or \
            _derive_machine_type_from_serial(serial)
        out.append(MyReservationEntry(
            id=r["id"],
            machine_id=r["machine_id"],
            serial_number=serial,
            machine_type=machine_type,
            status=r["status"],
            expires_at=r.get("expires_at"),
            created_at=r["created_at"],
        ))
    return out


def _build_my_issues(user_id: str) -> list[RecentIssueEntry]:
    """Last 5 issues reported by the given rep (Task 4.7).

    Unlike `_build_recent_issues` this isn't filtered by status — a rep
    looking at "my recent issues" wants to see the resolved ones too.
    """
    rows = (
        supabase_admin.table("machine_issues")
        .select(
            "id, machine_id, title, priority, status, reported_by, "
            "created_at, machines(serial_number, products(name))"
        )
        .eq("reported_by", user_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
        .data
        or []
    )
    out: list[RecentIssueEntry] = []
    for r in rows:
        machine_join = r.get("machines") or {}
        if isinstance(machine_join, dict):
            serial = machine_join.get("serial_number")
            product = machine_join.get("products")
            product_name = (
                product.get("name") if isinstance(product, dict) else None
            )
        else:
            serial = None
            product_name = None
        machine_type = _derive_machine_type(product_name) or \
            _derive_machine_type_from_serial(serial)
        out.append(RecentIssueEntry(
            id=r["id"],
            machine_id=r["machine_id"],
            serial_number=serial,
            machine_serial=serial,
            machine_type=machine_type,
            title=r["title"],
            priority=r["priority"],
            status=r["status"],
            reported_by=r.get("reported_by"),
            reported_by_name=None,  # rep is the caller — name not needed
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

        # Rep-only personal data (Sprint 4 Task 4.7). Admin gets `None` so the
        # frontend can branch on presence rather than role.
        my_reservations: Optional[list[MyReservationEntry]] = None
        my_issues: Optional[list[RecentIssueEntry]] = None
        if rep_filter_id is not None:
            try:
                my_reservations = _build_my_reservations(rep_filter_id)
            except Exception:
                my_reservations = []
            try:
                my_issues = _build_my_issues(rep_filter_id)
            except Exception:
                my_issues = []

        return DashboardSummaryResponse(
            machines=machines,
            warranties=warranties,
            issues=issues,
            reservations=reservations,
            low_stock=low_stock,
            recent_activity=recent_activity,
            recent_issues=recent_issues,
            open_issues=recent_issues,  # Sprint 4.4 — same payload, widget-friendly name
            expiring_warranties=expiring_warranties,
            expired_warranties=expired_warranties,
            my_reservations=my_reservations,
            my_issues=my_issues,
        )
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build dashboard summary: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/activity  (Sprint 4 Task 4.3 — dedicated paginated activity feed)
# ---------------------------------------------------------------------------

def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _resolve_machine_id(identifier: str) -> Optional[str]:
    """Accept UUID or serial_number; return the machine UUID (or None)."""
    if _is_uuid(identifier):
        return identifier
    result = (
        supabase_admin.table("machines")
        .select("id")
        .eq("serial_number", identifier)
        .execute()
    )
    return result.data[0]["id"] if result.data else None


def _derive_machine_type_from_serial(serial: Optional[str]) -> Optional[str]:
    """Serial like 'RX-2026-001' / 'RO-…' encodes the machine type as the prefix."""
    if not serial:
        return None
    upper = serial.upper()
    if upper.startswith("RX"):
        return "RX"
    if upper.startswith("RO"):
        return "RO"
    return None


def _format_time_ago(value) -> str:
    """Best-effort human-friendly relative time. Empty string on failure."""
    if not value:
        return ""
    try:
        s = str(value).replace("Z", "+00:00")
        then = datetime.fromisoformat(s)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return ""
    diff = (datetime.now(timezone.utc) - then).total_seconds()
    if diff < 60:
        return "just now"
    if diff < 3600:
        m = int(diff // 60)
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if diff < 86400:
        h = int(diff // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if diff < 86400 * 30:
        d = int(diff // 86400)
        return f"{d} day{'s' if d != 1 else ''} ago"
    return then.strftime("%b %d, %Y")


@router.get("/activity", response_model=list[ActivityFeedEntry])
def activity_feed(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    machine_id: Optional[str] = Query(None, description="UUID or serial number"),
    changed_by: Optional[str] = Query(None, description="profile UUID"),
    date_from: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    current_user: dict = Depends(get_current_user),
):
    """Paginated machine status change log.

    Joins machines (serial_number, product name) and profiles (full_name).
    Friendly identifier accepted for `machine_id` (UUID or serial number).
    All filters optional; `limit` capped at 50.
    """
    q = (
        supabase_admin.table("machine_status_log")
        .select(
            "id, machine_id, from_status, to_status, changed_by, reason, "
            "created_at, machines(serial_number, products(name)), "
            "profiles(full_name)"
        )
        .order("created_at", desc=True)
    )

    if machine_id:
        resolved = _resolve_machine_id(machine_id)
        if resolved is None:
            # Unknown machine — return empty rather than 404; UI just shows nothing.
            return []
        q = q.eq("machine_id", resolved)

    if changed_by:
        q = q.eq("changed_by", changed_by)

    if date_from:
        q = q.gte("created_at", date_from)

    if date_to:
        # Inclusive end-of-day for a plain YYYY-MM-DD.
        end_value = date_to if "T" in date_to else f"{date_to}T23:59:59+00:00"
        q = q.lte("created_at", end_value)

    rows = q.range(offset, offset + limit - 1).execute().data or []

    out: list[ActivityFeedEntry] = []
    for r in rows:
        machine_join = r.get("machines") or {}
        serial = (
            machine_join.get("serial_number")
            if isinstance(machine_join, dict) else None
        )
        product = (
            machine_join.get("products") if isinstance(machine_join, dict) else None
        )
        product_name = (
            product.get("name") if isinstance(product, dict) else None
        )
        prof_join = r.get("profiles") or {}
        full_name = (
            prof_join.get("full_name")
            if isinstance(prof_join, dict) else None
        )
        # Type from product name first, fall back to serial prefix.
        machine_type = _derive_machine_type(product_name) or \
            _derive_machine_type_from_serial(serial)

        out.append(ActivityFeedEntry(
            id=r["id"],
            machine_id=r["machine_id"],
            machine_serial=serial,
            serial_number=serial,
            machine_type=machine_type,
            from_status=r.get("from_status"),
            to_status=r["to_status"],
            changed_by=r.get("changed_by"),
            changed_by_name=full_name,
            reason=r.get("reason"),
            created_at=r["created_at"],
            time_ago=_format_time_ago(r["created_at"]),
        ))
    return out


# ---------------------------------------------------------------------------
# GET /api/dashboard/report  (Sprint 4 Task 4.6 — daily / weekly summary)
# ---------------------------------------------------------------------------

VALID_PERIODS = ("daily", "weekly")


def _count_in(table: str, time_col: str, since_iso: str, **eq_filters) -> int:
    """COUNT(*) helper — `time_col >= since_iso` plus optional `=` filters."""
    q = supabase_admin.table(table).select("id", count="exact").gte(time_col, since_iso)
    for k, v in eq_filters.items():
        q = q.eq(k, v)
    try:
        return q.execute().count or 0
    except Exception:
        return 0


def _count_between(table: str, time_col: str, since_iso: str, until_iso: str, **eq_filters) -> int:
    """COUNT(*) helper — `time_col` between two ISO timestamps."""
    q = (
        supabase_admin.table(table)
        .select("id", count="exact")
        .gte(time_col, since_iso)
        .lte(time_col, until_iso)
    )
    for k, v in eq_filters.items():
        q = q.eq(k, v)
    try:
        return q.execute().count or 0
    except Exception:
        return 0


def _avg_resolution_hours(since_iso: str) -> Optional[float]:
    """Average hours between created_at and updated_at for issues resolved
    or closed in the given period. `None` if no qualifying issues."""
    try:
        rows = (
            supabase_admin.table("machine_issues")
            .select("created_at, updated_at, status")
            .in_("status", ["resolved", "closed"])
            .gte("updated_at", since_iso)
            .execute()
            .data
            or []
        )
    except Exception:
        return None

    total_hours = 0.0
    n = 0
    for r in rows:
        created = _parse_ts(r.get("created_at"))
        updated = _parse_ts(r.get("updated_at"))
        if created and updated and updated >= created:
            total_hours += (updated - created).total_seconds() / 3600
            n += 1
    return round(total_hours / n, 2) if n else None


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _build_top_rep(since_iso: str) -> ReportTopRep:
    """Rep with the most reservations created in period."""
    try:
        rows = (
            supabase_admin.table("reservations")
            .select("reserved_by")
            .gte("created_at", since_iso)
            .execute()
            .data
            or []
        )
    except Exception:
        return ReportTopRep()

    counts: dict[str, int] = {}
    for r in rows:
        uid = r.get("reserved_by")
        if uid:
            counts[uid] = counts.get(uid, 0) + 1
    if not counts:
        return ReportTopRep()
    top_uid, top_count = max(counts.items(), key=lambda kv: kv[1])

    name: Optional[str] = None
    try:
        prof = (
            supabase_admin.table("profiles")
            .select("full_name")
            .eq("id", top_uid)
            .execute()
            .data
            or []
        )
        if prof:
            name = prof[0].get("full_name")
    except Exception:
        pass
    return ReportTopRep(name=name, reservations=top_count)


def _low_stock_count() -> int:
    """Reuse the low-stock builder's logic to count items currently below threshold."""
    try:
        return _build_low_stock().count
    except Exception:
        return 0


@router.get("/dashboard/report", response_model=SummaryReportResponse)
def dashboard_report(
    period: str = "daily",
    current_user: dict = Depends(get_current_user),
):
    """Daily (last 24h) or weekly (last 7d) snapshot of activity.

    All counts use `created_at >= period_start`; warranty `expired_in_period`
    uses `end_date` between period_start and today. Each section is
    best-effort — a query failure surfaces zeros for that section, not a
    500 for the whole report.
    """
    if period not in VALID_PERIODS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"period must be one of {VALID_PERIODS}",
        )

    now = datetime.now(timezone.utc)
    days_back = 1 if period == "daily" else 7
    period_start_dt = now - timedelta(days=days_back)
    since_iso = period_start_dt.isoformat()
    today = now.date()

    # ── Machines ────────────────────────────────────────────────────
    try:
        machines = ReportMachines(
            registered=_count_in("machines", "created_at", since_iso),
            status_changes=_count_in("machine_status_log", "created_at", since_iso),
            delivered=_count_in(
                "machine_status_log", "created_at", since_iso, to_status="delivered"
            ),
        )
    except Exception:
        machines = ReportMachines()

    # ── Warranties ──────────────────────────────────────────────────
    try:
        created_count = _count_in("warranty", "created_at", since_iso)

        # expiring_this_week: end_date in [today, today + 7 days]
        next_week_iso = (today + timedelta(days=7)).isoformat()
        try:
            expiring_count = (
                supabase_admin.table("warranty")
                .select("id", count="exact")
                .gte("end_date", today.isoformat())
                .lte("end_date", next_week_iso)
                .execute()
                .count
                or 0
            )
        except Exception:
            expiring_count = 0

        # expired_in_period: end_date between period_start.date() and today (inclusive)
        try:
            expired_count = (
                supabase_admin.table("warranty")
                .select("id", count="exact")
                .gte("end_date", period_start_dt.date().isoformat())
                .lte("end_date", today.isoformat())
                .execute()
                .count
                or 0
            )
        except Exception:
            expired_count = 0

        warranties = ReportWarranties(
            created=created_count,
            expiring_this_week=expiring_count,
            expired_in_period=expired_count,
        )
    except Exception:
        warranties = ReportWarranties()

    # ── Reservations ────────────────────────────────────────────────
    # `created` filters on created_at; the rest filter on updated_at since
    # the row changes status without creating a new row.
    try:
        reservations = ReportReservations(
            created=_count_in("reservations", "created_at", since_iso),
            approved=_count_in("reservations", "updated_at", since_iso, status="approved"),
            denied=_count_in("reservations", "updated_at", since_iso, status="denied"),
            expired=_count_in("reservations", "updated_at", since_iso, status="expired"),
        )
    except Exception:
        reservations = ReportReservations()

    # ── Issues ──────────────────────────────────────────────────────
    try:
        issues = ReportIssues(
            opened=_count_in("machine_issues", "created_at", since_iso),
            resolved=(
                _count_in("machine_issues", "updated_at", since_iso, status="resolved")
                + _count_in("machine_issues", "updated_at", since_iso, status="closed")
            ),
            average_resolution_hours=_avg_resolution_hours(since_iso),
        )
    except Exception:
        issues = ReportIssues()

    # ── Stock ───────────────────────────────────────────────────────
    try:
        stock = ReportStock(
            batches_added=_count_in("consumable_batches", "created_at", since_iso),
            shipments=_count_in("consumable_batches", "shipped_date", since_iso),
            low_stock_items=_low_stock_count(),
        )
    except Exception:
        stock = ReportStock()

    # ── Top rep ─────────────────────────────────────────────────────
    try:
        top_rep = _build_top_rep(since_iso)
    except Exception:
        top_rep = ReportTopRep()

    return SummaryReportResponse(
        period=period,
        date_range=ReportDateRange(
            from_date=period_start_dt.date(),
            to_date=today,
        ),
        machines=machines,
        warranties=warranties,
        reservations=reservations,
        issues=issues,
        stock=stock,
        top_rep=top_rep,
    )
