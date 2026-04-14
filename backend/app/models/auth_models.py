from datetime import datetime
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    tier: str | None = None
    account_status: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserProfile


class AdminSetupRequest(BaseModel):
    email: str
    password: str
    full_name: str
    admin_code: str


class AdminSetupResponse(BaseModel):
    success: bool
    message: str
    is_first_account: bool


class GenerateAdminCodeRequest(BaseModel):
    note: str | None = None


class AdminCodeResponse(BaseModel):
    code: str
    created_at: datetime
    note: str | None = None


class InviteRequest(BaseModel):
    email: str
    full_name: str
    tier: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
