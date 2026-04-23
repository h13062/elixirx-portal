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
