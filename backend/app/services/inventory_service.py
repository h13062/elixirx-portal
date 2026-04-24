from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.supabase_client import supabase_admin
from app.models.inventory_models import (
    BatchCreate,
    BatchReport,
    BatchReportByFlavor,
    BatchReportSummary,
    BatchResponse,
    BatchShipRequest,
    BatchUpdate,
    ConsumableStockResponse,
    MachineCreate,
    MachineResponse,
    ProductCreate,
    ProductUpdate,
    StockUpdate,
    SupplementFlavorCreate,
    SupplementFlavorResponse,
    SupplementFlavorUpdate,
)
from app.repositories.admin_code_repository import AdminLogRepository
from app.repositories.batch_repository import BatchRepository
from app.repositories.machine_repository import MachineRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.stock_repository import StockRepository
from app.repositories.supplement_flavor_repository import SupplementFlavorRepository


class InventoryService:
    """Business logic for all inventory operations."""

    def __init__(self) -> None:
        self._products = ProductRepository(supabase_admin)
        self._machines = MachineRepository(supabase_admin)
        self._stock = StockRepository(supabase_admin)
        self._audit = AdminLogRepository(supabase_admin)
        self._flavors = SupplementFlavorRepository(supabase_admin)
        self._batches = BatchRepository(supabase_admin)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

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
    def _build_stock_response(row: dict, batch_count: int = 0) -> ConsumableStockResponse:
        product = row.get("products") or {}
        return ConsumableStockResponse(
            product_id=row["product_id"],
            product_name=product.get("name", ""),
            product_sku=product.get("sku"),
            default_price=product.get("default_price", 0.0),
            description=product.get("description"),
            quantity=row["quantity"],
            min_threshold=row.get("min_threshold"),
            alert_enabled=row.get("alert_enabled"),
            batch_count=batch_count,
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _build_batch_response(row: dict) -> BatchResponse:
        product = row.get("products") or {}
        flavor = row.get("supplement_flavors") or {}
        return BatchResponse(
            id=row["id"],
            product_id=row["product_id"],
            product_name=product.get("name") if isinstance(product, dict) else None,
            product_sku=product.get("sku") if isinstance(product, dict) else None,
            flavor_id=row.get("flavor_id"),
            flavor_name=flavor.get("name") if isinstance(flavor, dict) else None,
            flavor_sku=flavor.get("sku") if isinstance(flavor, dict) else None,
            batch_number=row["batch_number"],
            quantity_manufactured=row["quantity_manufactured"],
            quantity=row["quantity"],
            quantity_shipped=row["quantity_shipped"],
            manufacture_date=row["manufacture_date"],
            expiry_date=row.get("expiry_date"),
            shipped_date=row.get("shipped_date"),
            shipped_to=row.get("shipped_to"),
            status=row["status"],
            notes=row.get("notes"),
            added_by=row.get("added_by"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _recalculate_stock(self, product_id: str) -> None:
        total = self._batches.sum_quantity_for_product(product_id)
        self._stock.recalculate_from_batches(product_id, total, self._now_iso())

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

    def create_product(self, payload: ProductCreate, created_by: str):
        try:
            if self._products.sku_exists(payload.sku):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU '{payload.sku}' already exists",
                )
            if payload.category not in ("consumable", "machine"):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="category must be 'consumable' or 'machine'",
                )

            now_iso = self._now_iso()
            created = self._products.create({
                "name": payload.name,
                "sku": payload.sku,
                "category": payload.category,
                "default_price": payload.default_price,
                "description": payload.description,
                "is_serialized": payload.is_serialized or False,
                "is_active": True,
                "created_at": now_iso,
                "updated_at": now_iso,
            })
            if not created:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create product",
                )

            if payload.category == "consumable":
                self._stock.create(created["id"])

            return created
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create product: {e}",
            )

    def update_product(self, identifier: str, payload: ProductUpdate):
        try:
            product = self._products.find_by_identifier(identifier)
            if not product:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Product not found")

            if payload.sku and payload.sku != product.get("sku"):
                if self._products.sku_exists(payload.sku, exclude_id=product["id"]):
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"SKU '{payload.sku}' already exists",
                    )

            data = {k: v for k, v in payload.model_dump().items() if v is not None}
            data["updated_at"] = self._now_iso()
            updated = self._products.update(product["id"], data)
            if not updated:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update product",
                )
            return updated
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update product: {e}",
            )

    # -------------------------------------------------------------------------
    # Supplement flavors
    # -------------------------------------------------------------------------

    def list_supplement_flavors(self) -> list[SupplementFlavorResponse]:
        try:
            flavors = self._flavors.list_active()
            stats = self._batches.get_batch_stats_by_flavor()
            result = []
            for f in flavors:
                fid = f["id"]
                s = stats.get(fid, {})
                result.append(SupplementFlavorResponse(
                    id=fid,
                    name=f["name"],
                    sku=f.get("sku"),
                    description=f.get("description"),
                    default_price=f.get("default_price"),
                    is_active=f["is_active"],
                    sort_order=f.get("sort_order", 0),
                    total_in_stock=s.get("total_in_stock", 0),
                    batch_count=s.get("batch_count", 0),
                ))
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch supplement flavors: {e}",
            )

    def create_supplement_flavor(
        self, payload: SupplementFlavorCreate, created_by: str
    ) -> SupplementFlavorResponse:
        try:
            if self._flavors.sku_exists(payload.sku):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"SKU '{payload.sku}' already exists",
                )
            created = self._flavors.create({
                "name": payload.name,
                "sku": payload.sku,
                "description": payload.description,
                "default_price": payload.default_price,
                "sort_order": payload.sort_order or 0,
                "is_active": True,
            })
            if not created:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create flavor",
                )
            return SupplementFlavorResponse(
                id=created["id"],
                name=created["name"],
                sku=created.get("sku"),
                description=created.get("description"),
                default_price=created.get("default_price"),
                is_active=created["is_active"],
                sort_order=created.get("sort_order", 0),
                total_in_stock=0,
                batch_count=0,
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create flavor: {e}",
            )

    def update_supplement_flavor(
        self, identifier: str, payload: SupplementFlavorUpdate
    ) -> SupplementFlavorResponse:
        try:
            flavor = self._flavors.find_by_identifier(identifier)
            if not flavor:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Flavor not found")

            if payload.sku and payload.sku != flavor.get("sku"):
                if self._flavors.sku_exists(payload.sku, exclude_id=flavor["id"]):
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"SKU '{payload.sku}' already exists",
                    )

            data = {k: v for k, v in payload.model_dump().items() if v is not None}
            updated = self._flavors.update(flavor["id"], data)
            if not updated:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update flavor",
                )
            stats = self._batches.get_batch_stats_by_flavor()
            s = stats.get(flavor["id"], {})
            return SupplementFlavorResponse(
                id=updated["id"],
                name=updated["name"],
                sku=updated.get("sku"),
                description=updated.get("description"),
                default_price=updated.get("default_price"),
                is_active=updated["is_active"],
                sort_order=updated.get("sort_order", 0),
                total_in_stock=s.get("total_in_stock", 0),
                batch_count=s.get("batch_count", 0),
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update flavor: {e}",
            )

    def delete_supplement_flavor(self, identifier: str) -> None:
        try:
            flavor = self._flavors.find_by_identifier(identifier)
            if not flavor:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Flavor not found")
            self._flavors.soft_delete(flavor["id"])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete flavor: {e}",
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

            now_iso = self._now_iso()
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
            rows = self._stock.list_all()
            batch_counts = self._batches.get_batch_counts_by_product()
            return [
                self._build_stock_response(r, batch_counts.get(r["product_id"], 0))
                for r in rows
            ]
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
            batch_counts = self._batches.get_batch_counts_by_product()
            return self._build_stock_response(row, batch_counts.get(product["id"], 0))
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
        try:
            product = self._products.find_by_identifier(product_id)
            if not product:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail=f"Product not found: {product_id}",
                )
            if not self._stock.exists(product["id"]):
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND,
                    detail="Product not found in consumable stock",
                )

            # Update thresholds
            if payload.min_threshold is not None or payload.alert_enabled is not None:
                self._stock.update_thresholds(
                    product["id"], payload.min_threshold, payload.alert_enabled
                )

            # Direct quantity override (backward compat)
            if payload.quantity is not None:
                if payload.quantity < 0:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail="Quantity must be >= 0",
                    )
                now_iso = self._now_iso()
                self._stock.update(product["id"], payload.quantity, updated_by, now_iso)
                self._audit.log("update_stock", actor_id=updated_by)

            row = self._stock.find_by_product(product["id"])
            if not row:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Stock updated but could not be retrieved",
                )
            batch_counts = self._batches.get_batch_counts_by_product()
            return self._build_stock_response(row, batch_counts.get(product["id"], 0))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update stock: {e}",
            )

    # -------------------------------------------------------------------------
    # Consumable batches
    # -------------------------------------------------------------------------

    def list_batches(
        self,
        product_id: str | None,
        flavor_id: str | None,
    ) -> list[BatchResponse]:
        try:
            resolved_product_id = None
            resolved_flavor_id = None
            if product_id:
                product = self._products.find_by_identifier(product_id)
                if not product:
                    raise HTTPException(
                        status.HTTP_404_NOT_FOUND,
                        detail=f"Product not found: {product_id}",
                    )
                resolved_product_id = product["id"]
            if flavor_id:
                flavor = self._flavors.find_by_identifier(flavor_id)
                if not flavor:
                    raise HTTPException(
                        status.HTTP_404_NOT_FOUND,
                        detail=f"Flavor not found: {flavor_id}",
                    )
                resolved_flavor_id = flavor["id"]
            rows = self._batches.list_all(resolved_product_id, resolved_flavor_id)
            return [self._build_batch_response(r) for r in rows]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch batches: {e}",
            )

    def create_batch(self, payload: BatchCreate, added_by: str) -> BatchResponse:
        try:
            product = self._products.find_by_identifier(payload.product_id)
            if not product:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Product not found: {payload.product_id}",
                )

            is_supplement = "supplement" in product["name"].lower()

            # Validate flavor requirement
            if is_supplement and not payload.flavor_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="flavor_id is required for Supplement Pack batches",
                )
            if not is_supplement and payload.flavor_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="flavor_id must not be provided for non-supplement products",
                )

            resolved_flavor_id = None
            if payload.flavor_id:
                flavor = self._flavors.find_by_identifier(payload.flavor_id)
                if not flavor:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"Flavor not found: {payload.flavor_id}",
                    )
                resolved_flavor_id = flavor["id"]

            now_iso = self._now_iso()
            data: dict = {
                "product_id": product["id"],
                "batch_number": payload.batch_number,
                "quantity_manufactured": payload.quantity_manufactured,
                "quantity": payload.quantity_manufactured,
                "quantity_shipped": 0,
                "manufacture_date": payload.manufacture_date.isoformat(),
                "status": "in_stock",
                "added_by": added_by,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            if resolved_flavor_id:
                data["flavor_id"] = resolved_flavor_id
            if payload.expiry_date:
                data["expiry_date"] = payload.expiry_date.isoformat()
            if payload.notes:
                data["notes"] = payload.notes

            created = self._batches.create(data)
            if not created:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create batch",
                )

            self._recalculate_stock(product["id"])

            row = self._batches.find_by_id(created["id"])
            if not row:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Batch created but could not be retrieved",
                )
            return self._build_batch_response(row)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create batch: {e}",
            )

    def update_batch(self, batch_id: str, payload: BatchUpdate) -> BatchResponse:
        try:
            batch = self._batches.find_by_id(batch_id)
            if not batch:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Batch not found")

            data: dict = {}
            if payload.quantity is not None:
                data["quantity"] = payload.quantity
            if payload.batch_number is not None:
                data["batch_number"] = payload.batch_number
            if payload.notes is not None:
                data["notes"] = payload.notes
            if payload.expiry_date is not None:
                data["expiry_date"] = payload.expiry_date.isoformat()
            data["updated_at"] = self._now_iso()

            self._batches.update(batch_id, data)
            self._recalculate_stock(batch["product_id"])

            row = self._batches.find_by_id(batch_id)
            if not row:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Batch updated but could not be retrieved",
                )
            return self._build_batch_response(row)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update batch: {e}",
            )

    def delete_batch(self, batch_id: str) -> None:
        try:
            batch = self._batches.find_by_id(batch_id)
            if not batch:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Batch not found")
            product_id = batch["product_id"]
            self._batches.delete(batch_id)
            self._recalculate_stock(product_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete batch: {e}",
            )

    def ship_batch(self, batch_id: str, payload: BatchShipRequest) -> BatchResponse:
        try:
            batch = self._batches.find_by_id(batch_id)
            if not batch:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Batch not found")

            current_qty = batch["quantity"]
            if payload.quantity_to_ship <= 0:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="quantity_to_ship must be > 0",
                )
            if payload.quantity_to_ship > current_qty:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot ship {payload.quantity_to_ship} — only {current_qty} in stock",
                )

            new_qty = current_qty - payload.quantity_to_ship
            new_shipped = batch["quantity_shipped"] + payload.quantity_to_ship
            new_status = (
                "fully_shipped" if new_qty == 0
                else "partially_shipped" if new_shipped > 0
                else "in_stock"
            )

            self._batches.update(batch_id, {
                "quantity": new_qty,
                "quantity_shipped": new_shipped,
                "shipped_date": payload.shipped_date.isoformat(),
                "shipped_to": payload.shipped_to,
                "status": new_status,
                "updated_at": self._now_iso(),
            })
            self._recalculate_stock(batch["product_id"])

            row = self._batches.find_by_id(batch_id)
            if not row:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Batch shipped but could not be retrieved",
                )
            return self._build_batch_response(row)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to ship batch: {e}",
            )

    def get_batch_report(
        self,
        product_id: str | None,
        flavor_id: str | None,
        date_from: str | None,
        date_to: str | None,
    ) -> BatchReport:
        try:
            resolved_product_id = None
            resolved_flavor_id = None
            if product_id:
                product = self._products.find_by_identifier(product_id)
                if not product:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Product not found")
                resolved_product_id = product["id"]
            if flavor_id:
                flavor = self._flavors.find_by_identifier(flavor_id)
                if not flavor:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Flavor not found")
                resolved_flavor_id = flavor["id"]

            rows = self._batches.list_all(resolved_product_id, resolved_flavor_id)

            # Apply date filters in Python
            if date_from:
                rows = [r for r in rows if r["manufacture_date"] >= date_from]
            if date_to:
                rows = [r for r in rows if r["manufacture_date"] <= date_to]

            total_manufactured = sum(r["quantity_manufactured"] for r in rows)
            total_in_stock = sum(r["quantity"] for r in rows)
            total_shipped = sum(r["quantity_shipped"] for r in rows)

            # Group by flavor
            by_flavor: dict[str, dict] = {}
            for r in rows:
                fid = r.get("flavor_id") or "__none__"
                fl = r.get("supplement_flavors") or {}
                fname = fl.get("name", "N/A") if isinstance(fl, dict) else "N/A"
                fsku = fl.get("sku") if isinstance(fl, dict) else None
                if fid not in by_flavor:
                    by_flavor[fid] = {
                        "flavor_id": r.get("flavor_id"),
                        "flavor_name": fname,
                        "flavor_sku": fsku,
                        "manufactured": 0,
                        "in_stock": 0,
                        "shipped": 0,
                    }
                by_flavor[fid]["manufactured"] += r["quantity_manufactured"]
                by_flavor[fid]["in_stock"] += r["quantity"]
                by_flavor[fid]["shipped"] += r["quantity_shipped"]

            return BatchReport(
                summary=BatchReportSummary(
                    total_manufactured=total_manufactured,
                    total_in_stock=total_in_stock,
                    total_shipped=total_shipped,
                    batch_count=len(rows),
                ),
                by_flavor=[
                    BatchReportByFlavor(**v) for v in by_flavor.values()
                ],
                batches=[self._build_batch_response(r) for r in rows],
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate report: {e}",
            )
