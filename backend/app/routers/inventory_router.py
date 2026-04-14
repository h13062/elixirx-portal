from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user, require_admin
from app.core.supabase_client import supabase_admin
from app.models.inventory_models import (
    ConsumableStockResponse,
    MachineCreate,
    MachineResponse,
    ProductResponse,
    StockUpdate,
    SupplementFlavorResponse,
)

router = APIRouter(prefix="/api", tags=["inventory"])


def _derive_machine_type(product_name: str) -> str | None:
    if product_name.upper().startswith("RX"):
        return "RX"
    if product_name.upper().startswith("RO"):
        return "RO"
    return None


def _build_machine_response(row: dict) -> MachineResponse:
    product = row.get("products") or {}
    product_name = product.get("name") if isinstance(product, dict) else None
    machine_type = _derive_machine_type(product_name) if product_name else None
    return MachineResponse(
        id=row["id"],
        serial_number=row["serial_number"],
        product_id=row["product_id"],
        product_name=product_name,
        machine_type=machine_type,
        batch_number=row["batch_number"],
        manufacture_date=row["manufacture_date"],
        status=row["status"],
        reserved_by=row.get("reserved_by"),
        reservation_expires_at=row.get("reservation_expires_at"),
        registered_by=row["registered_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# GET /api/products
# ---------------------------------------------------------------------------

@router.get("/products", response_model=list[ProductResponse])
def list_products(current_user: dict = Depends(get_current_user)):
    try:
        resp = (
            supabase_admin.table("products")
            .select("*")
            .eq("is_active", True)
            .order("name")
            .execute()
        )
        return resp.data or []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch products: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/supplement-flavors
# ---------------------------------------------------------------------------

@router.get("/supplement-flavors", response_model=list[SupplementFlavorResponse])
def list_supplement_flavors(current_user: dict = Depends(get_current_user)):
    try:
        resp = (
            supabase_admin.table("supplement_flavors")
            .select("*")
            .eq("is_active", True)
            .order("sort_order")
            .execute()
        )
        return resp.data or []
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch supplement flavors: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/machines
# ---------------------------------------------------------------------------

@router.get("/machines", response_model=list[MachineResponse])
def list_machines(
    machine_status: str | None = Query(default=None, alias="status"),
    machine_type: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    try:
        query = (
            supabase_admin.table("machines")
            .select("*, products(name)")
            .order("created_at", desc=True)
        )
        if machine_status:
            query = query.eq("status", machine_status)

        resp = query.execute()
        rows = resp.data or []

        if machine_type:
            prefix = machine_type.upper()
            rows = [
                r for r in rows
                if isinstance(r.get("products"), dict)
                and r["products"].get("name", "").upper().startswith(prefix)
            ]

        return [_build_machine_response(r) for r in rows]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch machines: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/machines/{machine_id}
# ---------------------------------------------------------------------------

@router.get("/machines/{machine_id}", response_model=MachineResponse)
def get_machine(machine_id: str, current_user: dict = Depends(get_current_user)):
    try:
        resp = (
            supabase_admin.table("machines")
            .select("*, products(name)")
            .eq("id", machine_id)
            .execute()
        )
        if not resp.data or len(resp.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
        return _build_machine_response(resp.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch machine: {str(e)}",
        )


# ---------------------------------------------------------------------------
# POST /api/machines  (admin only)
# ---------------------------------------------------------------------------

@router.post("/machines", response_model=MachineResponse, status_code=201)
def create_machine(
    payload: MachineCreate,
    current_user: dict = Depends(require_admin),
):
    try:
        # Check serial number uniqueness
        sn_resp = (
            supabase_admin.table("machines")
            .select("id")
            .eq("serial_number", payload.serial_number)
            .execute()
        )
        if sn_resp.data and len(sn_resp.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Serial number already exists",
            )

        # Validate product exists and is serialized
        product_resp = (
            supabase_admin.table("products")
            .select("id, is_serialized")
            .eq("id", payload.product_id)
            .execute()
        )
        if not product_resp.data or len(product_resp.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product not found",
            )
        if not product_resp.data[0].get("is_serialized"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product is not a serialized product",
            )

        # Insert machine
        now_iso = datetime.now(timezone.utc).isoformat()
        insert_resp = (
            supabase_admin.table("machines")
            .insert({
                "serial_number": payload.serial_number,
                "product_id": payload.product_id,
                "batch_number": payload.batch_number,
                "manufacture_date": payload.manufacture_date.isoformat(),
                "status": "available",
                "registered_by": current_user["id"],
                "created_at": now_iso,
                "updated_at": now_iso,
            })
            .execute()
        )
        if not insert_resp.data or len(insert_resp.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create machine",
            )

        machine_id = insert_resp.data[0]["id"]

        # Fetch with product join to build full response
        fetch_resp = (
            supabase_admin.table("machines")
            .select("*, products(name)")
            .eq("id", machine_id)
            .execute()
        )
        if not fetch_resp.data or len(fetch_resp.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Machine created but could not be retrieved",
            )
        return _build_machine_response(fetch_resp.data[0])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create machine: {str(e)}",
        )


# ---------------------------------------------------------------------------
# GET /api/consumable-stock
# ---------------------------------------------------------------------------

@router.get("/consumable-stock", response_model=list[ConsumableStockResponse])
def list_consumable_stock(current_user: dict = Depends(get_current_user)):
    try:
        resp = (
            supabase_admin.table("consumable_stock")
            .select("product_id, quantity, updated_at, products(name, sku, default_price)")
            .order("products(name)")
            .execute()
        )
        rows = resp.data or []
        result = []
        for row in rows:
            product = row.get("products") or {}
            result.append(ConsumableStockResponse(
                product_id=row["product_id"],
                product_name=product.get("name", ""),
                product_sku=product.get("sku"),
                default_price=product.get("default_price", 0.0),
                quantity=row["quantity"],
                updated_at=row["updated_at"],
            ))
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch consumable stock: {str(e)}",
        )


# ---------------------------------------------------------------------------
# PUT /api/consumable-stock/{product_id}  (admin only)
# ---------------------------------------------------------------------------

@router.put("/consumable-stock/{product_id}", response_model=ConsumableStockResponse)
def update_consumable_stock(
    product_id: str,
    payload: StockUpdate,
    current_user: dict = Depends(require_admin),
):
    if payload.quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quantity must be >= 0",
        )

    try:
        # Fetch existing stock row
        existing_resp = (
            supabase_admin.table("consumable_stock")
            .select("product_id, quantity, updated_at, products(name, sku, default_price)")
            .eq("product_id", product_id)
            .execute()
        )
        if not existing_resp.data or len(existing_resp.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found in consumable stock",
            )

        old_row = existing_resp.data[0]
        old_quantity = old_row["quantity"]

        now_iso = datetime.now(timezone.utc).isoformat()
        update_resp = (
            supabase_admin.table("consumable_stock")
            .update({
                "quantity": payload.quantity,
                "updated_by": current_user["id"],
                "updated_at": now_iso,
            })
            .eq("product_id", product_id)
            .execute()
        )
        if not update_resp.data or len(update_resp.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update stock",
            )

        # Audit log — wrapped so a log failure never breaks the response
        try:
            supabase_admin.table("admin_log").insert({
                "event": "update_stock",
                "actor_id": current_user["id"],
            }).execute()
        except Exception:
            pass

        # Re-fetch with product join for the response
        refreshed_resp = (
            supabase_admin.table("consumable_stock")
            .select("product_id, quantity, updated_at, products(name, sku, default_price)")
            .eq("product_id", product_id)
            .execute()
        )
        if not refreshed_resp.data or len(refreshed_resp.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stock updated but could not be retrieved",
            )

        row = refreshed_resp.data[0]
        product = row.get("products") or {}
        return ConsumableStockResponse(
            product_id=row["product_id"],
            product_name=product.get("name", ""),
            product_sku=product.get("sku"),
            default_price=product.get("default_price", 0.0),
            quantity=row["quantity"],
            updated_at=row["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update stock: {str(e)}",
        )
