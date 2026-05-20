"""Dashboard response models (Sprint 4 Task 4.0).

The /api/dashboard/summary endpoint aggregates data from many tables in a
single round trip. These models describe the response shape — they are
intentionally flat-by-section so the frontend can wire each card and section
to a top-level key without further reshaping.

For rep users the `reservations` and `issues` sections are filtered to the
caller's own data; everything else (machines, warranties, low_stock,
recent_activity, expiring_warranties) is global since those are operational
facts, not personal.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class DashboardMachineCounts(BaseModel):
    total: int = 0
    available: int = 0
    reserved: int = 0
    ordered: int = 0
    sold: int = 0
    delivered: int = 0
    returned: int = 0


class DashboardWarrantyCounts(BaseModel):
    active: int = 0
    expiring_soon: int = 0
    expired: int = 0
    total: int = 0


class DashboardIssueCounts(BaseModel):
    open: int = 0
    in_progress: int = 0
    resolved: int = 0
    closed: int = 0
    urgent: int = 0
    high: int = 0
    total: int = 0


class DashboardReservationCounts(BaseModel):
    pending: int = 0
    approved: int = 0
    denied: int = 0
    expired: int = 0
    cancelled: int = 0
    converted: int = 0
    total: int = 0


class LowStockItem(BaseModel):
    product_id: str
    product_name: str
    sku: Optional[str] = None
    quantity: int
    min_threshold: int


class DashboardLowStock(BaseModel):
    count: int
    total_tracked: int = 0
    items: list[LowStockItem]


class RecentActivityEntry(BaseModel):
    id: str
    machine_id: str
    serial_number: Optional[str] = None
    from_status: Optional[str] = None
    to_status: str
    changed_by: Optional[str] = None
    changed_by_name: Optional[str] = None
    reason: Optional[str] = None
    created_at: datetime


class ActivityFeedEntry(BaseModel):
    """Dedicated /api/activity payload (Sprint 4 Task 4.3).

    Adds machine_type + time_ago compared to RecentActivityEntry so the
    standalone activity-feed page can render without further reshaping.
    """
    id: str
    machine_id: str
    machine_serial: Optional[str] = None
    serial_number: Optional[str] = None  # alias kept for older clients
    machine_type: Optional[str] = None
    from_status: Optional[str] = None
    to_status: str
    changed_by: Optional[str] = None
    changed_by_name: Optional[str] = None
    reason: Optional[str] = None
    created_at: datetime
    time_ago: str


class ExpiringWarrantyEntry(BaseModel):
    warranty_id: str
    machine_id: str
    serial_number: Optional[str] = None
    machine_type: Optional[str] = None
    customer_name: Optional[str] = None
    end_date: date
    duration_months: int
    days_remaining: int


class ExpiredWarrantyEntry(BaseModel):
    warranty_id: str
    machine_id: str
    serial_number: Optional[str] = None
    machine_type: Optional[str] = None
    customer_name: Optional[str] = None
    end_date: date
    days_overdue: int


class RecentIssueEntry(BaseModel):
    id: str
    machine_id: str
    serial_number: Optional[str] = None
    machine_serial: Optional[str] = None  # alias kept stable for the widget
    machine_type: Optional[str] = None    # RX / RO (Task 4.4)
    title: str
    priority: str
    status: str
    reported_by: Optional[str] = None
    reported_by_name: Optional[str] = None
    created_at: datetime


class MyReservationEntry(BaseModel):
    """A rep's own recent reservation (Sprint 4 Task 4.7)."""
    id: str
    machine_id: str
    serial_number: Optional[str] = None
    machine_type: Optional[str] = None
    status: str
    expires_at: Optional[datetime] = None
    created_at: datetime


class DashboardSummaryResponse(BaseModel):
    machines: DashboardMachineCounts
    warranties: DashboardWarrantyCounts
    issues: DashboardIssueCounts
    reservations: DashboardReservationCounts
    low_stock: DashboardLowStock
    recent_activity: list[RecentActivityEntry]
    recent_issues: list[RecentIssueEntry]
    # `open_issues` is the same payload as `recent_issues`, exposed under the
    # name the Sprint 4.4 issue-tracker widget consumes.
    open_issues: list[RecentIssueEntry]
    expiring_warranties: list[ExpiringWarrantyEntry]
    expired_warranties: list[ExpiredWarrantyEntry]
    # Rep-only personal data. `None` for admins so admins don't accidentally
    # render an empty "my issues" list. (Sprint 4 Task 4.7.)
    my_reservations: Optional[list[MyReservationEntry]] = None
    my_issues: Optional[list[RecentIssueEntry]] = None


# ─── Summary report (Sprint 4 Task 4.6) ───────────────────────────────────

class ReportDateRange(BaseModel):
    """Inclusive date range that the report covers."""
    from_date: date
    to_date: date


class ReportMachines(BaseModel):
    registered: int = 0
    status_changes: int = 0
    delivered: int = 0


class ReportWarranties(BaseModel):
    created: int = 0
    expiring_this_week: int = 0
    expired_in_period: int = 0


class ReportReservations(BaseModel):
    created: int = 0
    approved: int = 0
    denied: int = 0
    expired: int = 0


class ReportIssues(BaseModel):
    opened: int = 0
    resolved: int = 0
    average_resolution_hours: Optional[float] = None


class ReportStock(BaseModel):
    batches_added: int = 0
    shipments: int = 0
    low_stock_items: int = 0


class ReportTopRep(BaseModel):
    name: Optional[str] = None
    reservations: int = 0


class SummaryReportResponse(BaseModel):
    period: str  # "daily" | "weekly"
    date_range: ReportDateRange
    machines: ReportMachines
    warranties: ReportWarranties
    reservations: ReportReservations
    issues: ReportIssues
    stock: ReportStock
    top_rep: ReportTopRep
