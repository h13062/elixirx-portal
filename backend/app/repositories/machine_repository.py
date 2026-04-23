import uuid

from app.repositories.base import BaseRepository

_MACHINE_SELECT = "*, products(name, sku)"


class MachineRepository(BaseRepository):
    """Data access for the machines table."""

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except ValueError:
            return False

    def serial_exists(self, serial_number: str) -> bool:
        result = (
            self._db.table("machines")
            .select("id")
            .eq("serial_number", serial_number)
            .execute()
        )
        return bool(result.data)

    def find_by_identifier(self, identifier: str) -> dict | None:
        """Find by UUID or serial number, with product join."""
        if self._is_uuid(identifier):
            result = (
                self._db.table("machines")
                .select(_MACHINE_SELECT)
                .eq("id", identifier)
                .execute()
            )
        else:
            result = (
                self._db.table("machines")
                .select(_MACHINE_SELECT)
                .eq("serial_number", identifier)
                .execute()
            )
        return result.data[0] if result.data else None

    def find_by_id(self, machine_id: str) -> dict | None:
        result = (
            self._db.table("machines")
            .select(_MACHINE_SELECT)
            .eq("id", machine_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_all(self, machine_status: str | None = None) -> list[dict]:
        query = (
            self._db.table("machines")
            .select(_MACHINE_SELECT)
            .order("created_at", desc=True)
        )
        if machine_status:
            query = query.eq("status", machine_status)
        return query.execute().data or []

    def create(self, data: dict) -> dict | None:
        result = self._db.table("machines").insert(data).execute()
        return result.data[0] if result.data else None
