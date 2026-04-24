"""Inventory router — thin HTTP controller. Business logic lives in InventoryService."""

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user, require_admin
from app.models.inventory_models import (
    BatchCreate,
    BatchShipRequest,
    BatchUpdate,
    ConsumableStockResponse,
    MachineCreate,
    MachineResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    StockUpdate,
    SupplementFlavorCreate,
    SupplementFlavorResponse,
    SupplementFlavorUpdate,
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
# POST /api/products  (admin only)
# ---------------------------------------------------------------------------

@router.post("/products", response_model=ProductResponse, status_code=201)
def create_product(payload: ProductCreate, current_user: dict = Depends(require_admin)):
    return _inventory.create_product(payload, current_user["id"])


# ---------------------------------------------------------------------------
# PUT /api/products/{identifier}  (admin only)
# ---------------------------------------------------------------------------

@router.put("/products/{identifier}", response_model=ProductResponse)
def update_product(identifier: str, payload: ProductUpdate, current_user: dict = Depends(require_admin)):
    return _inventory.update_product(identifier, payload)


# ---------------------------------------------------------------------------
# GET /api/supplement-flavors
# ---------------------------------------------------------------------------

@router.get("/supplement-flavors", response_model=list[SupplementFlavorResponse])
def list_supplement_flavors(current_user: dict = Depends(get_current_user)):
    return _inventory.list_supplement_flavors()


# ---------------------------------------------------------------------------
# POST /api/supplement-flavors  (admin only)
# ---------------------------------------------------------------------------

@router.post("/supplement-flavors", response_model=SupplementFlavorResponse, status_code=201)
def create_supplement_flavor(
    payload: SupplementFlavorCreate,
    current_user: dict = Depends(require_admin),
):
    return _inventory.create_supplement_flavor(payload, current_user["id"])


# ---------------------------------------------------------------------------
# PUT /api/supplement-flavors/{identifier}  (admin only)
# ---------------------------------------------------------------------------

@router.put("/supplement-flavors/{identifier}", response_model=SupplementFlavorResponse)
def update_supplement_flavor(
    identifier: str,
    payload: SupplementFlavorUpdate,
    current_user: dict = Depends(require_admin),
):
    return _inventory.update_supplement_flavor(identifier, payload)


# ---------------------------------------------------------------------------
# DELETE /api/supplement-flavors/{identifier}  (admin only)
# ---------------------------------------------------------------------------

@router.delete("/supplement-flavors/{identifier}")
def delete_supplement_flavor(identifier: str, current_user: dict = Depends(require_admin)):
    _inventory.delete_supplement_flavor(identifier)
    return {"success": True, "message": "Flavor deactivated"}


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


# ---------------------------------------------------------------------------
# GET /api/consumable-batches
# ---------------------------------------------------------------------------

@router.get("/consumable-batches")
def list_batches(
    product_id: str | None = Query(default=None),
    flavor_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    return _inventory.list_batches(product_id, flavor_id)


# ---------------------------------------------------------------------------
# GET /api/consumable-batches/report
# NOTE: Must be registered BEFORE the /{batch_id} route so FastAPI doesn't
#       treat "report" as a batch_id.
# ---------------------------------------------------------------------------

@router.get("/consumable-batches/report")
def batch_report(
    product_id: str | None = Query(default=None),
    flavor_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    return _inventory.get_batch_report(product_id, flavor_id, date_from, date_to)


# ---------------------------------------------------------------------------
# POST /api/consumable-batches  (admin only)
# ---------------------------------------------------------------------------

@router.post("/consumable-batches", status_code=201)
def create_batch(payload: BatchCreate, current_user: dict = Depends(require_admin)):
    return _inventory.create_batch(payload, current_user["id"])


# ---------------------------------------------------------------------------
# PUT /api/consumable-batches/{batch_id}  (admin only)
# ---------------------------------------------------------------------------

@router.put("/consumable-batches/{batch_id}")
def update_batch(
    batch_id: str,
    payload: BatchUpdate,
    current_user: dict = Depends(require_admin),
):
    return _inventory.update_batch(batch_id, payload)


# ---------------------------------------------------------------------------
# DELETE /api/consumable-batches/{batch_id}  (admin only)
# ---------------------------------------------------------------------------

@router.delete("/consumable-batches/{batch_id}")
def delete_batch(batch_id: str, current_user: dict = Depends(require_admin)):
    _inventory.delete_batch(batch_id)
    return {"success": True, "message": "Batch deleted"}


# ---------------------------------------------------------------------------
# POST /api/consumable-batches/{batch_id}/ship  (admin only)
# ---------------------------------------------------------------------------

@router.post("/consumable-batches/{batch_id}/ship")
def ship_batch(
    batch_id: str,
    payload: BatchShipRequest,
    current_user: dict = Depends(require_admin),
):
    return _inventory.ship_batch(batch_id, payload)
