from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.supabase_client import supabase, supabase_admin

bearer_scheme = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    """Validate the Bearer token and return the user's profile."""
    token = credentials.credentials
    try:
        # Use supabase_admin so token verification never contaminates the regular client's session
        user_resp = supabase_admin.auth.get_user(token)
        user = user_resp.user
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    profile_resp = (
        supabase.table("profiles")
        .select("*")
        .eq("id", user.id)
        .execute()
    )
    if not profile_resp.data or len(profile_resp.data) == 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User profile not found")

    return profile_resp.data[0]


def require_admin(profile: dict = Depends(get_current_user)) -> dict:
    """Allow admins and super_admins."""
    if profile.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return profile


def require_super_admin(profile: dict = Depends(get_current_user)) -> dict:
    """Allow super_admins only."""
    if profile.get("role") != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return profile
