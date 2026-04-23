"""Inventory router — thin HTTP controller. Business logic lives in InventoryService."""

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user, require_admin
from app.models.inventory_models import (
    ConsumableStockResponse,
    MachineCreate,
    MachineResponse,
    ProductResponse,
    StockUpdate,
    SupplementFlavorResponse,
)
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/api", tags=["inventory"])
_inventory = InventoryService()


# ---------------------------------------------------------------------------
# GET /api/products
# ---------------------------------------------------------------------------

@router.get("/products", response_model=list[ProductResponse])
def list_products(current_user: dict = Depends(get_current_user)):
    return _inventory.list_products()


# ---------------------------------------------------------------------------
# GET /api/supplement-flavors
# ---------------------------------------------------------------------------

@router.get("/supplement-flavors", response_model=list[SupplementFlavorResponse])
def list_supplement_flavors(current_user: dict = Depends(get_current_user)):
    return _inventory.list_supplement_flavors()


# ---------------------------------------------------------------------------
# GET /api/machines
# ---------------------------------------------------------------------------

@router.get("/machines", response_model=list[MachineResponse])
def list_machines(
    machine_status: str | None = Query(default=None, alias="status"),
    machine_type: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    return _inventory.list_machines(machine_status, machine_type)


# ---------------------------------------------------------------------------
# GET /api/machines/{machine_id}  — accepts UUID or serial_number
# ---------------------------------------------------------------------------

@router.get("/machines/{machine_id}", response_model=MachineResponse)
def get_machine(machine_id: str, current_user: dict = Depends(get_current_user)):
    return _inventory.get_machine(machine_id)


# ---------------------------------------------------------------------------
# POST /api/machines  (admin only)
# ---------------------------------------------------------------------------

@router.post("/machines", response_model=MachineResponse, status_code=201)
def create_machine(payload: MachineCreate, current_user: dict = Depends(require_admin)):
    return _inventory.create_machine(payload, current_user["id"])


# ---------------------------------------------------------------------------
# GET /api/consumable-stock
# ---------------------------------------------------------------------------

@router.get("/consumable-stock", response_model=list[ConsumableStockResponse])
def list_consumable_stock(current_user: dict = Depends(get_current_user)):
    return _inventory.list_consumable_stock()


# ---------------------------------------------------------------------------
# GET /api/consumable-stock/{product_id}  — accepts UUID, SKU, or name
# ---------------------------------------------------------------------------

@router.get("/consumable-stock/{product_id}", response_model=ConsumableStockResponse)
def get_consumable_stock(product_id: str, current_user: dict = Depends(get_current_user)):
    return _inventory.get_consumable_stock(product_id)


# ---------------------------------------------------------------------------
# PUT /api/consumable-stock/{product_id}  (admin only)
# ---------------------------------------------------------------------------

@router.put("/consumable-stock/{product_id}", response_model=ConsumableStockResponse)
def update_consumable_stock(
    product_id: str,
    payload: StockUpdate,
    current_user: dict = Depends(require_admin),
):
    return _inventory.update_consumable_stock(product_id, payload, current_user["id"])
