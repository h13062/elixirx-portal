import uuid

from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository):
    """Data access for the products table."""

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except ValueError:
            return False

    def find_by_identifier(self, identifier: str) -> dict | None:
        """Resolve a product by UUID, SKU (exact), or name (case-insensitive)."""
        if self._is_uuid(identifier):
            result = self._db.table("products").select("*").eq("id", identifier).execute()
        else:
            result = self._db.table("products").select("*").eq("sku", identifier).execute()
            if not result.data:
                result = self._db.table("products").select("*").ilike("name", identifier).execute()
        return result.data[0] if result.data else None

    def list_active(self) -> list[dict]:
        result = (
            self._db.table("products")
            .select("*")
            .eq("is_active", True)
            .order("name")
            .execute()
        )
        return result.data or []

    def sku_exists(self, sku: str, exclude_id: str | None = None) -> bool:
        result = self._db.table("products").select("id").eq("sku", sku).execute()
        if not result.data:
            return False
        if exclude_id:
            return any(row["id"] != exclude_id for row in result.data)
        return True

    def create(self, data: dict) -> dict | None:
        result = self._db.table("products").insert(data).execute()
        return result.data[0] if result.data else None

    def update(self, product_id: str, data: dict) -> dict | None:
        result = (
            self._db.table("products")
            .update(data)
            .eq("id", product_id)
            .execute()
        )
        return result.data[0] if result.data else None
