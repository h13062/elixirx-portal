from app.repositories.base import BaseRepository

_LOG_SELECT = (
    "id, machine_id, from_status, to_status, changed_by, reason, created_at, "
    "profiles:changed_by(name)"
)


class MachineStatusLogRepository(BaseRepository):
    """Data access for the machine_status_log table."""

    def create(self, data: dict) -> dict | None:
        result = self._db.table("machine_status_log").insert(data).execute()
        return result.data[0] if result.data else None

    def list_for_machine(self, machine_id: str, limit: int | None = None) -> list[dict]:
        query = (
            self._db.table("machine_status_log")
            .select(_LOG_SELECT)
            .eq("machine_id", machine_id)
            .order("created_at", desc=True)
        )
        if limit is not None:
            query = query.limit(limit)
        return query.execute().data or []
