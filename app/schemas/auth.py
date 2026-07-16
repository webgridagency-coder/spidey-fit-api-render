"""
Authentication schemas.
"""

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    """Payload for creating a confirmed email/password account."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class SignupResponse(BaseModel):
    """Response after a user account is ready for password login."""

    user_id: str
    email: str
    confirmed: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class AccountUser(BaseModel):
    id: str
    email: EmailStr


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AccountUser


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)
    password: str = Field(..., min_length=8, max_length=128)
