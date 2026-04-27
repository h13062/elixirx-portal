from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

class ProductResponse(BaseModel):
    id: str
    name: str
    category: str
    default_price: float
    sku: Optional[str] = None
    description: Optional[str] = None
    is_serialized: bool
    is_active: bool


class ProductCreate(BaseModel):
    name: str
    sku: str
    category: str
    default_price: float
    description: Optional[str] = None
    is_serialized: Optional[bool] = False


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    default_price: Optional[float] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Machines
# ---------------------------------------------------------------------------

class MachineCreate(BaseModel):
    serial_number: str
    product_id: str
    batch_number: str
    manufacture_date: date


class MachineResponse(BaseModel):
    id: str
    serial_number: str
    product_id: str
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    machine_type: Optional[str] = None
    batch_number: str
    manufacture_date: date
    status: str
    reserved_by: Optional[str] = None
    reservation_expires_at: Optional[datetime] = None
    registered_by: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Consumable stock
# ---------------------------------------------------------------------------

class ConsumableStockResponse(BaseModel):
    product_id: str
    product_name: str
    product_sku: Optional[str] = None
    default_price: float
    description: Optional[str] = None
    quantity: int
    min_threshold: Optional[int] = None
    alert_enabled: Optional[bool] = None
    batch_count: int = 0
    updated_at: datetime


class StockUpdate(BaseModel):
    quantity: Optional[int] = None
    min_threshold: Optional[int] = None
    alert_enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# Supplement flavors
# ---------------------------------------------------------------------------

class SupplementFlavorResponse(BaseModel):
    id: str
    name: str
    sku: Optional[str] = None
    description: Optional[str] = None
    default_price: Optional[float] = None
    is_active: bool
    sort_order: int
    total_in_stock: int = 0
    batch_count: int = 0


class SupplementFlavorCreate(BaseModel):
    name: str
    sku: str
    description: Optional[str] = None
    default_price: Optional[float] = None
    sort_order: Optional[int] = 0


class SupplementFlavorUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    default_price: Optional[float] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


# ---------------------------------------------------------------------------
# Consumable batches
# ---------------------------------------------------------------------------

class BatchResponse(BaseModel):
    id: str
    product_id: str
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    flavor_id: Optional[str] = None
    flavor_name: Optional[str] = None
    flavor_sku: Optional[str] = None
    batch_number: str
    quantity_manufactured: int
    quantity: int
    quantity_shipped: int
    manufacture_date: date
    expiry_date: Optional[date] = None
    shipped_date: Optional[date] = None
    shipped_to: Optional[str] = None
    status: str
    notes: Optional[str] = None
    added_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BatchCreate(BaseModel):
    product_id: str
    batch_number: str
    quantity_manufactured: int
    manufacture_date: date
    flavor_id: Optional[str] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None


class BatchUpdate(BaseModel):
    quantity: Optional[int] = None
    batch_number: Optional[str] = None
    notes: Optional[str] = None
    expiry_date: Optional[date] = None


class BatchShipRequest(BaseModel):
    quantity_to_ship: int
    shipped_date: date
    shipped_to: str


class BatchReportSummary(BaseModel):
    total_manufactured: int
    total_in_stock: int
    total_shipped: int
    batch_count: int


class BatchReportByFlavor(BaseModel):
    flavor_id: Optional[str]
    flavor_name: str
    flavor_sku: Optional[str]
    manufactured: int
    in_stock: int
    shipped: int


class BatchReport(BaseModel):
    summary: BatchReportSummary
    by_flavor: list[BatchReportByFlavor]
    batches: list[BatchResponse]


# ---------------------------------------------------------------------------
# Machine lifecycle (Sprint 3 / 6 — status transitions, history, full detail)
# ---------------------------------------------------------------------------

class MachineStatusUpdate(BaseModel):
    new_status: str
    reason: Optional[str] = None
    force: Optional[bool] = False


class MachineStatusUpdateResponse(BaseModel):
    machine: MachineResponse
    warranty_setup_required: bool = False


class MachineStatusLogEntry(BaseModel):
    id: str
    from_status: Optional[str] = None
    to_status: str
    changed_by: Optional[str] = None
    changed_by_name: Optional[str] = None
    reason: Optional[str] = None
    created_at: datetime


class WarrantyInfo(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    duration_months: Optional[int] = None


class ReservationInfo(BaseModel):
    id: str
    rep_id: Optional[str] = None
    rep_name: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class MachineIssueInfo(BaseModel):
    id: str
    title: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None


class MachineFullDetail(BaseModel):
    machine: MachineResponse
    product: Optional[ProductResponse] = None
    status_history: list[MachineStatusLogEntry] = []
    warranty: Optional[WarrantyInfo] = None
    active_reservation: Optional[ReservationInfo] = None
    open_issues: list[MachineIssueInfo] = []


class BulkStatusUpdate(BaseModel):
    machine_ids: list[str]
    new_status: str
    reason: Optional[str] = None
    force: Optional[bool] = False


class BulkStatusResult(BaseModel):
    updated: int
    failed: int
    errors: list[str] = []


class MachineStatusSummary(BaseModel):
    available: int = 0
    reserved: int = 0
    ordered: int = 0
    sold: int = 0
    delivered: int = 0
    returned: int = 0
    total: int = 0
