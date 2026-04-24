import uuid

from app.repositories.base import BaseRepository

_BATCH_SELECT = (
    "id, product_id, flavor_id, batch_number, quantity_manufactured, quantity, "
    "quantity_shipped, manufacture_date, expiry_date, shipped_date, shipped_to, "
    "status, notes, added_by, created_at, updated_at, "
    "products(name, sku), supplement_flavors(name, sku)"
)


class BatchRepository(BaseRepository):
    """Data access for the consumable_batches table."""

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except ValueError:
            return False

    def find_by_id(self, batch_id: str) -> dict | None:
        result = (
            self._db.table("consumable_batches")
            .select(_BATCH_SELECT)
            .eq("id", batch_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_all(
        self,
        product_id: str | None = None,
        flavor_id: str | None = None,
    ) -> list[dict]:
        query = self._db.table("consumable_batches").select(_BATCH_SELECT)
        if product_id:
            query = query.eq("product_id", product_id)
        if flavor_id:
            query = query.eq("flavor_id", flavor_id)
        result = query.order("manufacture_date", desc=True).execute()
        return result.data or []

    def create(self, data: dict) -> dict | None:
        result = self._db.table("consumable_batches").insert(data).execute()
        return result.data[0] if result.data else None

    def update(self, batch_id: str, data: dict) -> dict | None:
        result = (
            self._db.table("consumable_batches")
            .update(data)
            .eq("id", batch_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def delete(self, batch_id: str) -> None:
        self._db.table("consumable_batches").delete().eq("id", batch_id).execute()

    def sum_quantity_for_product(self, product_id: str) -> int:
        result = (
            self._db.table("consumable_batches")
            .select("quantity")
            .eq("product_id", product_id)
            .execute()
        )
        return sum(row.get("quantity", 0) for row in (result.data or []))

    def get_batch_counts_by_product(self) -> dict[str, int]:
        """Returns {product_id: count} for all products."""
        result = self._db.table("consumable_batches").select("product_id").execute()
        counts: dict[str, int] = {}
        for row in (result.data or []):
            pid = row["product_id"]
            counts[pid] = counts.get(pid, 0) + 1
        return counts

    def get_batch_stats_by_flavor(self) -> dict[str, dict]:
        """Returns {flavor_id: {total_in_stock, batch_count}} for all flavors."""
        result = self._db.table("consumable_batches").select("flavor_id, quantity").execute()
        stats: dict[str, dict] = {}
        for row in (result.data or []):
            fid = row.get("flavor_id")
            if not fid:
                continue
            if fid not in stats:
                stats[fid] = {"total_in_stock": 0, "batch_count": 0}
            stats[fid]["total_in_stock"] += row.get("quantity", 0)
            stats[fid]["batch_count"] += 1
        return stats
