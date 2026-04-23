from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.supabase_client import supabase_admin
from app.models.inventory_models import (
    ConsumableStockResponse,
    MachineCreate,
    MachineResponse,
    StockUpdate,
)
from app.repositories.admin_code_repository import AdminLogRepository
from app.repositories.machine_repository import MachineRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.stock_repository import StockRepository


class InventoryService:
    """Business logic for all inventory operations."""

    def __init__(self) -> None:
        self._products = ProductRepository(supabase_admin)
        self._machines = MachineRepository(supabase_admin)
        self._stock = StockRepository(supabase_admin)
        self._audit = AdminLogRepository(supabase_admin)

    # -------------------------------------------------------------------------
    # Private builders
    # -------------------------------------------------------------------------

    @staticmethod
    def _derive_machine_type(product_name: str) -> str | None:
        name = product_name.upper()
        if name.startswith("RX"):
            return "RX"
        if name.startswith("RO"):
            return "RO"
        return None

    @staticmethod
    def _build_machine_response(row: dict) -> MachineResponse:
        product = row.get("products") or {}
        product_name = product.get("name") if isinstance(product, dict) else None
        product_sku = product.get("sku") if isinstance(product, dict) else None
        machine_type = (
            InventoryService._derive_machine_type(product_name) if product_name else None
        )
        return MachineResponse(
            id=row["id"],
            serial_number=row["serial_number"],
            product_id=row["product_id"],
            product_name=product_name,
            product_sku=product_sku,
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

    @staticmethod
    def _build_stock_response(row: dict) -> ConsumableStockResponse:
        product = row.get("products") or {}
        return ConsumableStockResponse(
            product_id=row["product_id"],
            product_name=product.get("name", ""),
            product_sku=product.get("sku"),
            default_price=product.get("default_price", 0.0),
            quantity=row["quantity"],
            updated_at=row["updated_at"],
        )

    # -------------------------------------------------------------------------
    # Products
    # -------------------------------------------------------------------------

    def list_products(self) -> list:
        try:
            return self._products.list_active()
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch products: {e}",
            )

    def list_supplement_flavors(self) -> list:
        try:
            result = (
                supabase_admin.table("supplement_flavors")
                .select("*")
                .eq("is_active", True)
                .order("sort_order")
                .execute()
            )
            return result.data or []
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch supplement flavors: {e}",
            )

    # -------------------------------------------------------------------------
    # Machines
    # -------------------------------------------------------------------------

    def list_machines(
        self,
        machine_status: str | None,
        machine_type: str | None,
    ) -> list[MachineResponse]:
        try:
            rows = self._machines.list_all(machine_status)
            if machine_type:
                prefix = machine_type.upper()
                rows = [
                    r for r in rows
                    if isinstance(r.get("products"), dict)
                    and r["products"].get("name", "").upper().startswith(prefix)
                ]
            return [self._build_machine_response(r) for r in rows]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch machines: {e}",
            )

    def get_machine(self, identifier: str) -> MachineResponse:
        try:
            row = self._machines.find_by_identifier(identifier)
            if not row:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Machine not found")
            return self._build_machine_response(row)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch machine: {e}",
            )

    def create_machine(self, payload: MachineCreate, registered_by: str) -> MachineResponse:
        try:
            if self._machines.serial_exists(payload.serial_number):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Serial number already exists",
                )

            product = self._products.find_by_identifier(payload.product_id)
            if not product:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Product not found: {payload.product_id}",
                )
            if not product.get("is_serialized"):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Product is not a serialized product",
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            created = self._machines.create({
                "serial_number": payload.serial_number,
                "product_id": product["id"],
                "batch_number": payload.batch_number,
                "manufacture_date": payload.manufacture_date.isoformat(),
                "status": "available",
                "registered_by": registered_by,
                "created_at": now_iso,
                "updated_at": now_iso,
            })
            if not created:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create machine",
                )

            row = self._machines.find_by_id(created["id"])
            if not row:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Machine created but could not be retrieved",
                )
            return self._build_machine_response(row)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create machine: {e}",
            )

    # -------------------------------------------------------------------------
    # Consumable stock
    # -------------------------------------------------------------------------

    def list_consumable_stock(self) -> list[ConsumableStockResponse]:
        try:
            return [self._build_stock_response(r) for r in self._stock.list_all()]
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch consumable stock: {e}",
            )

    def get_consumable_stock(self, product_id: str) -> ConsumableStockResponse:
        try:
            product = self._products.find_by_identifier(product_id)
            if not product:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail=f"Product not found: {product_id}",
                )
            row = self._stock.find_by_product(product["id"])
            if not row:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail="Product not found in consumable stock",
                )
            return self._build_stock_response(row)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch consumable stock: {e}",
            )

    def update_consumable_stock(
        self,
        product_id: str,
        payload: StockUpdate,
        updated_by: str,
    ) -> ConsumableStockResponse:
        if payload.quantity < 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Quantity must be >= 0",
            )
        try:
            product = self._products.find_by_identifier(product_id)
            if not product:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail=f"Product not found: {product_id}",
                )
            if product.get("category") != "consumable":
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="This product is not a consumable",
                )

            product_uuid = product["id"]
            if not self._stock.exists(product_uuid):
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail="Product not found in consumable stock",
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            self._stock.update(product_uuid, payload.quantity, updated_by, now_iso)
            self._audit.log("update_stock", actor_id=updated_by)

            row = self._stock.find_by_product(product_uuid)
            if not row:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Stock updated but could not be retrieved",
                )
            return self._build_stock_response(row)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update stock: {e}",
            )
