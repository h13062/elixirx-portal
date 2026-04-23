import random
import secrets
import string
import traceback
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from gotrue.types import AdminUserAttributes

from app.core.config import ADMIN_SETUP_CODE
from app.core.supabase_client import supabase, supabase_admin
from app.models.auth_models import AdminCodeResponse, AdminSetupResponse, LoginResponse, UserProfile
from app.repositories.admin_code_repository import (
    AdminCodeRepository,
    AdminLogRepository,
    SystemConfigRepository,
)
from app.repositories.invitation_repository import InvitationRepository
from app.repositories.profile_repository import ProfileRepository


class AuthService:
    """Business logic for authentication, admin management, and user invitations."""

    def __init__(self) -> None:
        self._profiles = ProfileRepository(supabase)
        self._admin_codes = AdminCodeRepository(supabase)
        self._system_config = SystemConfigRepository(supabase)
        self._audit = AdminLogRepository(supabase)
        self._invitations = InvitationRepository(supabase)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _generate_admin_code() -> str:
        chars = string.ascii_uppercase + string.digits
        return "ADM-" + "".join(random.choices(chars, k=6))

    @staticmethod
    def _generate_temp_password() -> str:
        chars = string.ascii_letters + string.digits + "!@#$%"
        return "".join(secrets.choice(chars) for _ in range(12))

    def _admin_setup_enabled(self) -> bool:
        value = self._system_config.get("admin_setup_enabled")
        return value.lower() == "true" if value else True

    def _build_user_profile(self, profile: dict) -> UserProfile:
        return UserProfile(
            id=profile["id"],
            email=profile["email"],
            full_name=profile["full_name"],
            role=profile["role"],
            tier=profile.get("tier"),
            account_status=profile["account_status"],
        )

    def _create_auth_user(
        self, email: str, password: str, full_name: str, role: str
    ):
        try:
            resp = supabase_admin.auth.admin.create_user(
                AdminUserAttributes(
                    email=email,
                    password=password,
                    email_confirm=True,
                    user_metadata={"full_name": full_name, "role": role},
                )
            )
            print(f"User created: {resp.user.id}")
            return resp.user
        except Exception as e:
            print(f"CREATE_USER ERROR: {type(e).__name__}: {e}")
            print(traceback.format_exc())
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Create user failed: {type(e).__name__}: {e}",
            )

    def _insert_profile(
        self,
        user_id: str,
        email: str,
        full_name: str,
        role: str,
        tier: str | None = None,
        invited_by: str | None = None,
    ) -> None:
        data: dict = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "role": role,
            "account_status": "active",
        }
        if tier:
            data["tier"] = tier
        if invited_by:
            data["invited_by"] = invited_by
        try:
            self._profiles.create(data)
            print(f"Profile inserted for {user_id}")
        except Exception as e:
            print(f"PROFILE ERROR: {type(e).__name__}: {e}")
            print(traceback.format_exc())
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Profile insert failed: {type(e).__name__}: {e}",
            )

    # -------------------------------------------------------------------------
    # Auth
    # -------------------------------------------------------------------------

    def login(self, email: str, password: str) -> LoginResponse:
        try:
            auth_resp = supabase.auth.sign_in_with_password({"email": email, "password": password})
            session = auth_resp.session
            user = auth_resp.user
            if not session or not user:
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
            )

        profile = self._profiles.find_by_id(user.id)
        if not profile:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, detail="User profile not found"
            )
        if profile.get("account_status") != "active":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Your account is not active. Contact your administrator.",
            )

        return LoginResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user=self._build_user_profile(profile),
        )

    def get_profile(self, user_id: str) -> UserProfile:
        profile = self._profiles.find_by_id(user_id)
        if not profile:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, detail="User profile not found"
            )
        return self._build_user_profile(profile)

    def change_password(
        self, user_id: str, email: str, current_password: str, new_password: str
    ) -> None:
        try:
            supabase.auth.sign_in_with_password({"email": email, "password": current_password})
        except Exception:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
            )
        try:
            supabase_admin.auth.admin.update_user_by_id(
                user_id, AdminUserAttributes(password=new_password)
            )
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update password: {e}",
            )

    # -------------------------------------------------------------------------
    # Admin setup
    # -------------------------------------------------------------------------

    def admin_setup(
        self,
        email: str,
        password: str,
        full_name: str,
        admin_code: str,
        ip_address: str | None,
    ) -> AdminSetupResponse:
        if not self._admin_setup_enabled():
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Admin registration is currently disabled",
            )

        is_first = self._profiles.count() == 0

        try:
            if is_first:
                if admin_code != ADMIN_SETUP_CODE:
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN, detail="Invalid admin code"
                    )
                user = self._create_auth_user(email, password, full_name, "super_admin")
                self._insert_profile(str(user.id), email, full_name, "super_admin")
                self._audit.log(
                    "super_admin_created", target_id=str(user.id), ip_address=ip_address
                )
                return AdminSetupResponse(
                    success=True,
                    message="Super admin account created successfully",
                    is_first_account=True,
                )

            # Validate admin code from DB
            code_row = self._admin_codes.find_by_code(admin_code)
            if not code_row:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, detail="Invalid admin code"
                )
            if code_row["status"] != "active":
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail="Admin code has already been used or expired",
                )

            expires_at = datetime.fromisoformat(code_row["expires_at"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires_at:
                self._admin_codes.mark_expired(code_row["id"])
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, detail="Admin code has expired"
                )

            user = self._create_auth_user(email, password, full_name, "admin")
            self._insert_profile(str(user.id), email, full_name, "admin")

            now_iso = datetime.now(timezone.utc).isoformat()
            self._admin_codes.mark_used(code_row["id"], str(user.id), now_iso)
            self._audit.log(
                "admin_created",
                target_id=str(user.id),
                code_used=admin_code,
                ip_address=ip_address,
            )

            return AdminSetupResponse(
                success=True,
                message="Admin account created successfully",
                is_first_account=False,
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Server error: {e}"
            )

    def toggle_admin_setup(self, enabled: bool) -> None:
        self._system_config.set("admin_setup_enabled", str(enabled).lower())

    # -------------------------------------------------------------------------
    # Admin codes & log
    # -------------------------------------------------------------------------

    def generate_admin_code(self, generated_by: str, note: str | None) -> AdminCodeResponse:
        code = self._generate_admin_code()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=72)
        self._admin_codes.create({
            "code": code,
            "generated_by": generated_by,
            "note": note,
            "status": "active",
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        })
        return AdminCodeResponse(code=code, created_at=now, note=note)

    def list_admin_codes(self) -> list:
        return self._admin_codes.list_all()

    def get_admin_log(self) -> list:
        return self._audit.list_all()

    # -------------------------------------------------------------------------
    # Invitations
    # -------------------------------------------------------------------------

    def invite_user(
        self, email: str, full_name: str, tier: str, invited_by: str
    ) -> dict:
        if self._profiles.find_by_email(email):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="User already exists")

        temp_password = self._generate_temp_password()
        now_iso = datetime.now(timezone.utc).isoformat()

        invitation = self._invitations.create({
            "email": email,
            "tier": tier,
            "invited_by": invited_by,
            "status": "pending",
            "created_at": now_iso,
        })
        if not invitation:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create invitation record",
            )

        print(f"DEBUG: Creating user {email}")
        try:
            user = self._create_auth_user(email, temp_password, full_name, "rep")
        except HTTPException:
            self._invitations.delete(invitation["id"])
            raise

        try:
            self._insert_profile(
                str(user.id), email, full_name, "rep", tier=tier, invited_by=invited_by
            )
        except HTTPException as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User created but profile insert failed: {e.detail}",
            )

        self._invitations.update_status(invitation["id"], "accepted")
        return {
            "message": "Rep account created successfully",
            "email": email,
            "full_name": full_name,
            "tier": tier,
            "temporary_password": temp_password,
            "note": "Share these credentials with the rep. They can change their password after logging in.",
        }

    def list_invitations(self) -> list:
        try:
            return self._invitations.list_all()
        except Exception as e:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Server error: {e}"
            )

    def cancel_invitation(self, invitation_id: str) -> None:
        invitation = self._invitations.find_by_id(invitation_id)
        if not invitation:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invitation not found")
        if invitation["status"] != "pending":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Can only cancel pending invitations",
            )
        self._invitations.update_status(invitation_id, "cancelled")
