from app.repositories.base import BaseRepository


class InvitationRepository(BaseRepository):
    """Data access for the invitations table."""

    def find_by_id(self, invitation_id: str) -> dict | None:
        result = (
            self._db.table("invitations")
            .select("id, status")
            .eq("id", invitation_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def create(self, data: dict) -> dict | None:
        result = self._db.table("invitations").insert(data).execute()
        return result.data[0] if result.data else None

    def update_status(self, invitation_id: str, new_status: str) -> None:
        self._db.table("invitations").update({"status": new_status}).eq("id", invitation_id).execute()

    def delete(self, invitation_id: str) -> None:
        self._db.table("invitations").delete().eq("id", invitation_id).execute()

    def list_all(self) -> list[dict]:
        result = (
            self._db.table("invitations")
            .select("id, email, tier, status, invited_by, created_at, accepted_at")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
