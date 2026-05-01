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


class ExpiringWarrantyEntry(BaseModel):
    warranty_id: str
    machine_id: str
    serial_number: Optional[str] = None
    customer_name: Optional[str] = None
    end_date: date
    days_remaining: int


class RecentIssueEntry(BaseModel):
    id: str
    machine_id: str
    serial_number: Optional[str] = None
    title: str
    priority: str
    status: str
    reported_by: Optional[str] = None
    reported_by_name: Optional[str] = None
    created_at: datetime


class DashboardSummaryResponse(BaseModel):
    machines: DashboardMachineCounts
    warranties: DashboardWarrantyCounts
    issues: DashboardIssueCounts
    reservations: DashboardReservationCounts
    low_stock: DashboardLowStock
    recent_activity: list[RecentActivityEntry]
    recent_issues: list[RecentIssueEntry]
    expiring_warranties: list[ExpiringWarrantyEntry]
