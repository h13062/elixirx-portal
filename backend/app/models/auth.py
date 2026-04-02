from datetime import datetime
from pydantic import BaseModel


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
