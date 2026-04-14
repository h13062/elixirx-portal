from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class ProductResponse(BaseModel):
    id: str
    name: str
    category: str
    default_price: float
    sku: Optional[str] = None
    is_serialized: bool
    is_active: bool


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


class ConsumableStockResponse(BaseModel):
    product_id: str
    product_name: str
    product_sku: Optional[str] = None
    default_price: float
    quantity: int
    updated_at: datetime


class StockUpdate(BaseModel):
    quantity: int


class SupplementFlavorResponse(BaseModel):
    id: str
    name: str
    is_active: bool
    sort_order: int
