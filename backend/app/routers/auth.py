"""
Auth router — admin setup and admin code management.

=== Supabase migrations (run these in the Supabase SQL editor) ===

-- 1. Add super_admin to the user_role enum
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'super_admin';

-- 2. admin_codes table
CREATE TABLE IF NOT EXISTS admin_codes (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    code        TEXT        NOT NULL UNIQUE,
    generated_by UUID       NOT NULL REFERENCES profiles(id),
    used_by     UUID        REFERENCES profiles(id),
    note        TEXT,
    status      TEXT        NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'used', 'expired')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ
);

-- 3. system_config table (used for admin-setup toggle and other flags)
CREATE TABLE IF NOT EXISTS system_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO system_config (key, value) VALUES ('admin_setup_enabled', 'true')
ON CONFLICT (key) DO NOTHING;

-- 4. admin_log table
CREATE TABLE IF NOT EXISTS admin_log (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    event       TEXT        NOT NULL,
    actor_id    UUID        REFERENCES profiles(id),
    target_id   UUID        REFERENCES profiles(id),
    code_used   TEXT,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

import random
import string
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.auth import require_super_admin
from app.core.config import ADMIN_SETUP_CODE
from app.core.supabase_client import supabase
from app.models.auth import (
    AdminCodeResponse,
    AdminSetupRequest,
    AdminSetupResponse,
    GenerateAdminCodeRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _admin_setup_enabled() -> bool:
    resp = (
        supabase.table("system_config")
        .select("value")
        .eq("key", "admin_setup_enabled")
        .single()
        .execute()
    )
    if resp.data:
        return resp.data["value"].lower() == "true"
    return True  # default open if row missing


def _profile_count() -> int:
    resp = supabase.table("profiles").select("id", count="exact").execute()
    return resp.count or 0


def _generate_code() -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"ADM-{suffix}"


# ---------------------------------------------------------------------------
# POST /api/auth/admin-setup
# ---------------------------------------------------------------------------

@router.post("/admin-setup", response_model=AdminSetupResponse)
def admin_setup(payload: AdminSetupRequest, request: Request):
    if not _admin_setup_enabled():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin registration is currently disabled")

    is_first = _profile_count() == 0
    ip_address = request.client.host if request.client else None

    if is_first:
        # First account: validate against the master env-var code
        if payload.admin_code != ADMIN_SETUP_CODE:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin code")

        auth_resp = supabase.auth.admin.create_user({
            "email": payload.email,
            "password": payload.password,
            "email_confirm": True,
        })
        user = auth_resp.user
        if not user:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create auth user")

        supabase.table("profiles").insert({
            "id": user.id,
            "email": payload.email,
            "full_name": payload.full_name,
            "role": "super_admin",
            "account_status": "active",
        }).execute()

        supabase.table("admin_log").insert({
            "event": "super_admin_created",
            "target_id": user.id,
            "ip_address": ip_address,
        }).execute()

        return AdminSetupResponse(
            success=True,
            message="Super admin account created successfully",
            is_first_account=True,
        )

    # Not the first account: validate against the admin_codes table
    code_resp = (
        supabase.table("admin_codes")
        .select("*")
        .eq("code", payload.admin_code)
        .single()
        .execute()
    )
    code_row = code_resp.data
    if not code_row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin code")

    if code_row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin code has already been used or expired")

    expires_at = datetime.fromisoformat(code_row["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        supabase.table("admin_codes").update({"status": "expired"}).eq("id", code_row["id"]).execute()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin code has expired")

    auth_resp = supabase.auth.admin.create_user({
        "email": payload.email,
        "password": payload.password,
        "email_confirm": True,
    })
    user = auth_resp.user
    if not user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create auth user")

    supabase.table("profiles").insert({
        "id": user.id,
        "email": payload.email,
        "full_name": payload.full_name,
        "role": "admin",
        "account_status": "active",
    }).execute()

    now_iso = datetime.now(timezone.utc).isoformat()
    supabase.table("admin_codes").update({
        "status": "used",
        "used_by": user.id,
        "used_at": now_iso,
    }).eq("id", code_row["id"]).execute()

    supabase.table("admin_log").insert({
        "event": "admin_created",
        "target_id": user.id,
        "code_used": payload.admin_code,
        "ip_address": ip_address,
    }).execute()

    return AdminSetupResponse(
        success=True,
        message="Admin account created successfully",
        is_first_account=False,
    )


# ---------------------------------------------------------------------------
# POST /api/auth/admin-codes/generate  (super_admin only)
# ---------------------------------------------------------------------------

@router.post("/admin-codes/generate", response_model=AdminCodeResponse)
def generate_admin_code(
    payload: GenerateAdminCodeRequest,
    current_user: dict = Depends(require_super_admin),
):
    code = _generate_code()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=72)

    supabase.table("admin_codes").insert({
        "code": code,
        "generated_by": current_user["id"],
        "note": payload.note,
        "status": "active",
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }).execute()

    return AdminCodeResponse(code=code, created_at=now, note=payload.note)


# ---------------------------------------------------------------------------
# GET /api/auth/admin-codes  (super_admin only)
# ---------------------------------------------------------------------------

@router.get("/admin-codes")
def list_admin_codes(current_user: dict = Depends(require_super_admin)):
    resp = (
        supabase.table("admin_codes")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


# ---------------------------------------------------------------------------
# GET /api/auth/admin-log  (super_admin only)
# ---------------------------------------------------------------------------

@router.get("/admin-log")
def admin_log(current_user: dict = Depends(require_super_admin)):
    resp = (
        supabase.table("admin_log")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


# ---------------------------------------------------------------------------
# PUT /api/auth/admin-setup/toggle  (super_admin only)
# ---------------------------------------------------------------------------

class _ToggleBody(AdminSetupRequest):
    pass


from pydantic import BaseModel

class ToggleBody(BaseModel):
    enabled: bool


@router.put("/admin-setup/toggle")
def toggle_admin_setup(
    body: ToggleBody,
    current_user: dict = Depends(require_super_admin),
):
    supabase.table("system_config").upsert({
        "key": "admin_setup_enabled",
        "value": str(body.enabled).lower(),
    }).execute()
    state = "enabled" if body.enabled else "disabled"
    return {"success": True, "message": f"Admin setup is now {state}"}
