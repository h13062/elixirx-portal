"""
Auth router — thin HTTP controller. Business logic lives in AuthService.

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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.core.auth import get_current_user, require_admin, require_super_admin
from app.core.supabase_client import supabase_admin
from app.models.auth_models import (
    AdminCodeResponse,
    AdminSetupRequest,
    AdminSetupResponse,
    ChangePasswordRequest,
    GenerateAdminCodeRequest,
    InviteRequest,
    LoginRequest,
    LoginResponse,
    UserProfile,
)
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer()

router = APIRouter(prefix="/api/auth", tags=["auth"])
_auth = AuthService()

VALID_TIERS = {"distributor", "agent", "master_agent"}


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    return _auth.login(payload.email, payload.password)


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------

@router.post("/logout")
def logout():
    return {"success": True, "message": "Logged out"}


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserProfile)
def me(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        user_resp = supabase_admin.auth.get_user(token)
        user = user_resp.user
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return _auth.get_profile(str(user.id))


# ---------------------------------------------------------------------------
# POST /api/auth/admin-setup
# ---------------------------------------------------------------------------

@router.post("/admin-setup", response_model=AdminSetupResponse)
def admin_setup(payload: AdminSetupRequest, request: Request):
    ip = request.client.host if request.client else None
    return _auth.admin_setup(
        payload.email, payload.password, payload.full_name, payload.admin_code, ip
    )


# ---------------------------------------------------------------------------
# POST /api/auth/admin-codes/generate  (super_admin only)
# ---------------------------------------------------------------------------

@router.post("/admin-codes/generate", response_model=AdminCodeResponse)
def generate_admin_code(
    payload: GenerateAdminCodeRequest,
    current_user: dict = Depends(require_super_admin),
):
    return _auth.generate_admin_code(current_user["id"], payload.note)


# ---------------------------------------------------------------------------
# GET /api/auth/admin-codes  (super_admin only)
# ---------------------------------------------------------------------------

@router.get("/admin-codes")
def list_admin_codes(current_user: dict = Depends(require_super_admin)):
    return _auth.list_admin_codes()


# ---------------------------------------------------------------------------
# GET /api/auth/admin-log  (super_admin only)
# ---------------------------------------------------------------------------

@router.get("/admin-log")
def admin_log(current_user: dict = Depends(require_super_admin)):
    return _auth.get_admin_log()


# ---------------------------------------------------------------------------
# PUT /api/auth/admin-setup/toggle  (super_admin only)
# ---------------------------------------------------------------------------

class ToggleBody(BaseModel):
    enabled: bool


@router.put("/admin-setup/toggle")
def toggle_admin_setup(body: ToggleBody, current_user: dict = Depends(require_super_admin)):
    _auth.toggle_admin_setup(body.enabled)
    state = "enabled" if body.enabled else "disabled"
    return {"success": True, "message": f"Admin setup is now {state}"}


# ---------------------------------------------------------------------------
# POST /api/auth/invite  (admin or super_admin only)
# ---------------------------------------------------------------------------

@router.post("/invite", status_code=201)
def invite_user(payload: InviteRequest, current_user: dict = Depends(require_admin)):
    if payload.tier not in VALID_TIERS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be one of: {', '.join(sorted(VALID_TIERS))}",
        )
    return _auth.invite_user(payload.email, payload.full_name, payload.tier, current_user["id"])


# ---------------------------------------------------------------------------
# POST /api/auth/change-password
# ---------------------------------------------------------------------------

@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    _auth.change_password(
        current_user["id"],
        current_user["email"],
        payload.current_password,
        payload.new_password,
    )
    return {"message": "Password changed successfully"}


# ---------------------------------------------------------------------------
# GET /api/auth/invitations  (admin or super_admin only)
# ---------------------------------------------------------------------------

@router.get("/invitations")
def list_invitations(current_user: dict = Depends(require_admin)):
    return _auth.list_invitations()


# ---------------------------------------------------------------------------
# DELETE /api/auth/invitations/{invitation_id}  (admin or super_admin only)
# ---------------------------------------------------------------------------

@router.delete("/invitations/{invitation_id}")
def cancel_invitation(invitation_id: str, current_user: dict = Depends(require_admin)):
    _auth.cancel_invitation(invitation_id)
    return {"success": True, "message": "Invitation cancelled"}
