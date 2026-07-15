"""
Authentication API routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.config import settings
from app.database import get_supabase_service
from app.schemas.auth import SignupRequest, SignupResponse


router = APIRouter()


@router.post("/signup", status_code=status.HTTP_410_GONE)
async def signup(payload: SignupRequest):
    """
    Retired legacy admin-signup endpoint.

    Account creation now uses the standard Supabase browser flow so verification,
    provider redirects, and abuse controls remain within the authentication system.
    """
    del payload
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use the standard Supabase signup flow.",
    )


@router.post(
    "/dev-signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def dev_signup(
    payload: SignupRequest,
    client: Client = Depends(get_supabase_service),
):
    """Create a brand-new confirmed account for local development only.

    This route never looks up, updates, or resets an existing account. It is
    deliberately unavailable unless both the development environment and the
    explicit bypass flag are enabled.
    """
    if (
        settings.ENVIRONMENT.strip().lower() != "development"
        or not settings.ALLOW_DEV_AUTH_BYPASS
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    normalized_email = payload.email.strip().lower()
    try:
        created = client.auth.admin.create_user(
            {
                "email": normalized_email,
                "password": payload.password,
                "email_confirm": True,
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create this local test account. Try a new email address.",
        ) from exc

    if not created.user:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The authentication service did not return a user.",
        )

    return SignupResponse(
        user_id=str(created.user.id),
        email=created.user.email or normalized_email,
        confirmed=True,
    )
