from supabase import Client


class BaseRepository:
    """Wraps a Supabase client and exposes it to subclasses."""

    def __init__(self, client: Client) -> None:
        self._db = client
