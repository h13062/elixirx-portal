from app.repositories.base import BaseRepository

_STOCK_SELECT = (
    "product_id, quantity, updated_at, min_threshold, alert_enabled, "
    "products(name, sku, default_price, description)"
)


class StockRepository(BaseRepository):
    """Data access for the consumable_stock table."""

    def list_all(self) -> list[dict]:
        result = (
            self._db.table("consumable_stock")
            .select(_STOCK_SELECT)
            .order("products(name)")
            .execute()
        )
        return result.data or []

    def find_by_product(self, product_id: str) -> dict | None:
        result = (
            self._db.table("consumable_stock")
            .select(_STOCK_SELECT)
            .eq("product_id", product_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def exists(self, product_id: str) -> bool:
        result = (
            self._db.table("consumable_stock")
            .select("product_id")
            .eq("product_id", product_id)
            .execute()
        )
        return bool(result.data)

    def create(self, product_id: str) -> None:
        self._db.table("consumable_stock").insert({
            "product_id": product_id,
            "quantity": 0,
        }).execute()

    def update(self, product_id: str, quantity: int, updated_by: str, now_iso: str) -> None:
        self._db.table("consumable_stock").update({
            "quantity": quantity,
            "updated_by": updated_by,
            "updated_at": now_iso,
        }).eq("product_id", product_id).execute()

    def update_thresholds(
        self,
        product_id: str,
        min_threshold: int | None,
        alert_enabled: bool | None,
    ) -> None:
        data: dict = {}
        if min_threshold is not None:
            data["min_threshold"] = min_threshold
        if alert_enabled is not None:
            data["alert_enabled"] = alert_enabled
        if data:
            self._db.table("consumable_stock").update(data).eq("product_id", product_id).execute()

    def recalculate_from_batches(self, product_id: str, total: int, now_iso: str) -> None:
        self._db.table("consumable_stock").update({
            "quantity": total,
            "updated_at": now_iso,
        }).eq("product_id", product_id).execute()
