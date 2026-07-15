"""
Authentication schemas.
"""

from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    """Payload for creating a confirmed email/password account."""

    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)


class SignupResponse(BaseModel):
    """Response after a user account is ready for password login."""

    user_id: str
    email: str
    confirmed: bool = False
