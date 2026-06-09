"""
Authentication API routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.database import get_supabase_service
from app.schemas.auth import SignupRequest, SignupResponse


router = APIRouter()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _find_user_by_email(client: Client, email: str):
    page = 1
    per_page = 100

    while True:
        users = client.auth.admin.list_users(page=page, per_page=per_page)
        match = next((user for user in users if (user.email or "").lower() == email), None)
        if match:
            return match
        if len(users) < per_page:
            return None
        page += 1


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    client: Client = Depends(get_supabase_service),
):
    """
    Create a confirmed Supabase email/password user.

    Supabase email delivery can be unavailable on trial/default SMTP settings.
    This endpoint keeps signup usable by confirming accounts server-side with
    the service role key, then the frontend signs in using the normal client SDK.
    """
    email = _normalize_email(payload.email)

    try:
        created = client.auth.admin.create_user(
            {
                "email": email,
                "password": payload.password,
                "email_confirm": True,
            }
        )
        user = created.user
    except Exception as create_error:
        existing_user = _find_user_by_email(client, email)
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to create account. Please try a different email address.",
            ) from create_error

        try:
            updated = client.auth.admin.update_user_by_id(
                existing_user.id,
                {
                    "password": payload.password,
                    "email_confirm": True,
                },
            )
            user = updated.user
        except Exception as update_error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This account could not be prepared for login. Please try again.",
            ) from update_error

    return SignupResponse(
        user_id=user.id,
        email=user.email or email,
        confirmed=True,
    )
