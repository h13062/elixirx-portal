"""Shared lightweight helpers for routers that bypass the repository pattern."""

import uuid

from app.core.supabase_client import supabase_admin


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def lookup_machine(identifier: str) -> dict | None:
    """Find a machine by UUID or serial_number, with product join."""
    q = supabase_admin.table("machines").select("*, products(name, sku)")
    if is_uuid(identifier):
        q = q.eq("id", identifier)
    else:
        q = q.eq("serial_number", identifier)
    result = q.execute()
    return result.data[0] if result.data else None
