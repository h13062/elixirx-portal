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
import secrets
import string
import traceback
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from gotrue.types import AdminUserAttributes
from postgrest.exceptions import APIError
from pydantic import BaseModel

from app.core.auth import require_admin, require_super_admin
from app.core.config import ADMIN_SETUP_CODE
from app.core.supabase_client import supabase, supabase_admin
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

bearer_scheme = HTTPBearer()

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    try:
        auth_resp = supabase.auth.sign_in_with_password({"email": payload.email, "password": payload.password})
        session = auth_resp.session
        user = auth_resp.user
        if not session or not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    try:
        profile_resp = (
            supabase.table("profiles")
            .select("*")
            .eq("id", user.id)
            .execute()
        )
        if not profile_resp.data or len(profile_resp.data) == 0:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User profile not found")

        profile = profile_resp.data[0]

        if profile.get("account_status") != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active. Contact your administrator.",
            )

        return LoginResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user=UserProfile(
                id=profile["id"],
                email=profile["email"],
                full_name=profile["full_name"],
                role=profile["role"],
                tier=profile.get("tier"),
                account_status=profile["account_status"],
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Server error: {str(e)}")


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
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        profile_resp = (
            supabase.table("profiles")
            .select("*")
            .eq("id", user.id)
            .execute()
        )
        if not profile_resp.data or len(profile_resp.data) == 0:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User profile not found")

        profile = profile_resp.data[0]

        return UserProfile(
            id=profile["id"],
            email=profile["email"],
            full_name=profile["full_name"],
            role=profile["role"],
            tier=profile.get("tier"),
            account_status=profile["account_status"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Server error: {str(e)}")


def _admin_setup_enabled() -> bool:
    resp = (
        supabase.table("system_config")
        .select("value")
        .eq("key", "admin_setup_enabled")
        .execute()
    )
    if resp.data and len(resp.data) > 0:
        return resp.data[0]["value"].lower() == "true"
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

    try:
        if is_first:
            if payload.admin_code != ADMIN_SETUP_CODE:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin code")

            try:
                auth_resp = supabase_admin.auth.admin.create_user(
                    AdminUserAttributes(
                        email=payload.email,
                        password=payload.password,
                        email_confirm=True,
                        user_metadata={"full_name": payload.full_name, "role": "super_admin"},
                    )
                )
                print(f"User created successfully: {auth_resp.user.id}")
            except Exception as e:
                print(f"FULL CREATE_USER ERROR: {type(e).__name__}: {str(e)}")
                print(f"TRACEBACK: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail=f"Create user failed: {type(e).__name__}: {str(e)}")

            user = auth_resp.user
            if not user:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create auth user")

            try:
                supabase.table("profiles").insert({
                    "id": str(user.id),
                    "email": payload.email,
                    "full_name": payload.full_name,
                    "role": "super_admin",
                    "account_status": "active",
                }).execute()
                print(f"Profile inserted successfully for {user.id}")
            except Exception as e:
                print(f"FULL PROFILE ERROR: {type(e).__name__}: {str(e)}")
                print(f"TRACEBACK: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail=f"Profile insert failed: {type(e).__name__}: {str(e)}")

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
            .execute()
        )
        if not code_resp.data or len(code_resp.data) == 0:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin code")
        code_row = code_resp.data[0]

        if code_row["status"] != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin code has already been used or expired")

        expires_at = datetime.fromisoformat(code_row["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expires_at:
            supabase.table("admin_codes").update({"status": "expired"}).eq("id", code_row["id"]).execute()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin code has expired")

        try:
            auth_resp = supabase_admin.auth.admin.create_user(
                AdminUserAttributes(
                    email=payload.email,
                    password=payload.password,
                    email_confirm=True,
                    user_metadata={"full_name": payload.full_name, "role": "admin"},
                )
            )
            print(f"User created successfully: {auth_resp.user.id}")
        except Exception as e:
            print(f"FULL CREATE_USER ERROR: {type(e).__name__}: {str(e)}")
            print(f"TRACEBACK: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Create user failed: {type(e).__name__}: {str(e)}")

        user = auth_resp.user
        if not user:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create auth user")

        try:
            supabase.table("profiles").insert({
                "id": str(user.id),
                "email": payload.email,
                "full_name": payload.full_name,
                "role": "admin",
                "account_status": "active",
            }).execute()
            print(f"Profile inserted successfully for {user.id}")
        except Exception as e:
            print(f"FULL PROFILE ERROR: {type(e).__name__}: {str(e)}")
            print(f"TRACEBACK: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Profile insert failed: {type(e).__name__}: {str(e)}")

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

    except HTTPException:
        raise
    except APIError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Server error: {str(e)}")


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


# ---------------------------------------------------------------------------
# POST /api/auth/invite  (admin or super_admin only)
# ---------------------------------------------------------------------------

VALID_TIERS = {"distributor", "agent", "master_agent"}


@router.post("/invite", status_code=201)
def invite_user(
    payload: InviteRequest,
    current_user: dict = Depends(require_admin),
):
    if payload.tier not in VALID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be one of: {', '.join(sorted(VALID_TIERS))}",
        )

    try:
        # Check if email already exists in profiles
        existing_resp = (
            supabase.table("profiles")
            .select("id")
            .eq("email", payload.email)
            .execute()
        )
        if existing_resp.data and len(existing_resp.data) > 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

        # Generate temporary password
        chars = string.ascii_letters + string.digits + "!@#$%"
        temp_password = "".join(secrets.choice(chars) for _ in range(12))

        # Save invitation record first
        now_iso = datetime.now(timezone.utc).isoformat()
        insert_resp = (
            supabase.table("invitations")
            .insert({
                "email": payload.email,
                "tier": payload.tier,
                "invited_by": current_user["id"],
                "status": "pending",
                "created_at": now_iso,
            })
            .execute()
        )
        if not insert_resp.data or len(insert_resp.data) == 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create invitation record")

        invitation = insert_resp.data[0]

        # Create auth user
        print(f"DEBUG: About to create user with email: {payload.email}")
        print(f"DEBUG: Using supabase URL: {supabase.supabase_url}")
        try:
            auth_resp = supabase_admin.auth.admin.create_user(
                AdminUserAttributes(
                    email=payload.email,
                    password=temp_password,
                    email_confirm=True,
                    user_metadata={"full_name": payload.full_name, "role": "rep"},
                )
            )
            print(f"DEBUG: User created successfully: {auth_resp.user.id}")
        except Exception as e:
            print(f"DEBUG FULL ERROR: {type(e).__name__}: {e}")
            print(f"DEBUG TRACEBACK: {traceback.format_exc()}")
            # Roll back invitation record
            supabase.table("invitations").delete().eq("id", invitation["id"]).execute()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create user account: {type(e).__name__}: {str(e)}",
            )

        # Insert profile manually (trigger is disabled)
        try:
            supabase.table("profiles").insert({
                "id": str(auth_resp.user.id),
                "email": payload.email,
                "full_name": payload.full_name,
                "role": "rep",
                "tier": payload.tier,
                "account_status": "active",
                "invited_by": current_user["id"],
            }).execute()
        except Exception as profile_error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User created but profile insert failed: {str(profile_error)}",
            )

        # Mark invitation as accepted
        supabase.table("invitations").update({"status": "accepted"}).eq("id", invitation["id"]).execute()

        return {
            "message": "Rep account created successfully",
            "email": payload.email,
            "full_name": payload.full_name,
            "tier": payload.tier,
            "temporary_password": temp_password,
            "note": "Share these credentials with the rep. They can change their password after logging in.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Server error: {str(e)}")


# ---------------------------------------------------------------------------
# POST /api/auth/change-password
# ---------------------------------------------------------------------------

@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    token = credentials.credentials

    try:
        user_resp = supabase_admin.auth.get_user(token)
        user = user_resp.user
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    # Verify current password
    try:
        supabase.auth.sign_in_with_password({"email": user.email, "password": payload.current_password})
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    # Update to new password
    try:
        supabase_admin.auth.admin.update_user_by_id(
            user.id,
            AdminUserAttributes(password=payload.new_password),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update password: {str(e)}")

    return {"message": "Password changed successfully"}


# ---------------------------------------------------------------------------
# GET /api/auth/invitations  (admin or super_admin only)
# ---------------------------------------------------------------------------

@router.get("/invitations")
def list_invitations(current_user: dict = Depends(require_admin)):
    try:
        resp = (
            supabase.table("invitations")
            .select("id, email, tier, status, invited_by, created_at, accepted_at")
            .order("created_at", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Server error: {str(e)}")


# ---------------------------------------------------------------------------
# DELETE /api/auth/invitations/{invitation_id}  (admin or super_admin only)
# ---------------------------------------------------------------------------

@router.delete("/invitations/{invitation_id}")
def cancel_invitation(
    invitation_id: str,
    current_user: dict = Depends(require_admin),
):
    try:
        fetch_resp = (
            supabase.table("invitations")
            .select("id, status")
            .eq("id", invitation_id)
            .execute()
        )
        if not fetch_resp.data or len(fetch_resp.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

        invitation = fetch_resp.data[0]
        if invitation["status"] != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only cancel pending invitations")

        supabase.table("invitations").update({"status": "cancelled"}).eq("id", invitation_id).execute()

        return {"success": True, "message": "Invitation cancelled"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Server error: {str(e)}")
