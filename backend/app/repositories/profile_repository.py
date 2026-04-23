from app.repositories.base import BaseRepository


class ProfileRepository(BaseRepository):
    """Data access for the profiles table."""

    def find_by_id(self, user_id: str) -> dict | None:
        result = self._db.table("profiles").select("*").eq("id", user_id).execute()
        return result.data[0] if result.data else None

    def find_by_email(self, email: str) -> dict | None:
        result = self._db.table("profiles").select("id").eq("email", email).execute()
        return result.data[0] if result.data else None

    def create(self, data: dict) -> dict | None:
        result = self._db.table("profiles").insert(data).execute()
        return result.data[0] if result.data else None

    def count(self) -> int:
        result = self._db.table("profiles").select("id", count="exact").execute()
        return result.count or 0
