from app.repositories.base import BaseRepository


class AdminCodeRepository(BaseRepository):
    """Data access for the admin_codes table."""

    def find_by_code(self, code: str) -> dict | None:
        result = self._db.table("admin_codes").select("*").eq("code", code).execute()
        return result.data[0] if result.data else None

    def create(self, data: dict) -> dict | None:
        result = self._db.table("admin_codes").insert(data).execute()
        return result.data[0] if result.data else None

    def mark_used(self, code_id: str, user_id: str, now_iso: str) -> None:
        self._db.table("admin_codes").update({
            "status": "used",
            "used_by": user_id,
            "used_at": now_iso,
        }).eq("id", code_id).execute()

    def mark_expired(self, code_id: str) -> None:
        self._db.table("admin_codes").update({"status": "expired"}).eq("id", code_id).execute()

    def list_all(self) -> list[dict]:
        result = (
            self._db.table("admin_codes")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []


class SystemConfigRepository(BaseRepository):
    """Data access for the system_config table."""

    def get(self, key: str) -> str | None:
        result = self._db.table("system_config").select("value").eq("key", key).execute()
        return result.data[0]["value"] if result.data else None

    def set(self, key: str, value: str) -> None:
        self._db.table("system_config").upsert({"key": key, "value": value}).execute()


class AdminLogRepository(BaseRepository):
    """Data access for the admin_log table."""

    def log(self, event: str, **kwargs) -> None:
        """Insert an audit log entry — failures are intentionally swallowed."""
        try:
            self._db.table("admin_log").insert({"event": event, **kwargs}).execute()
        except Exception:
            pass

    def list_all(self) -> list[dict]:
        result = (
            self._db.table("admin_log")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
