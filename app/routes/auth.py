"""Ojas-owned account, session, and password recovery routes."""

from email.message import EmailMessage
import smtplib

from fastapi import APIRouter, Depends, HTTPException, Request, status
from supabase import Client

from app.config import settings
from app.database import get_supabase_service
from app.dependencies import get_current_user
from app.schemas.auth import (
    AccountUser,
    AuthResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
)
from app.services.local_auth_service import LocalAuthService


router = APIRouter()


def auth_response(account: dict) -> AuthResponse:
    return AuthResponse(
        access_token=LocalAuthService.create_access_token(account["id"], account["email"]),
        user=AccountUser(id=account["id"], email=account["email"]),
    )


def send_reset_email(email: str, reset_url: str) -> bool:
    if not all((settings.SMTP_HOST, settings.SMTP_USERNAME, settings.SMTP_PASSWORD, settings.SMTP_FROM_EMAIL)):
        return False
    message = EmailMessage()
    message["Subject"] = "Reset your Ojas AI password"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = email
    message.set_content(f"Your Ojas AI password reset link is valid for 30 minutes:\n\n{reset_url}\n")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)
    return True


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, client: Client = Depends(get_supabase_service)):
    service = LocalAuthService(client)
    try:
        return auth_response(service.create_account(str(payload.email), payload.password))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Account storage is not ready.") from exc


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, client: Client = Depends(get_supabase_service)):
    account = LocalAuthService(client).authenticate(str(payload.email), payload.password)
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    return auth_response(account)


@router.get("/me", response_model=AccountUser)
async def me(user: dict = Depends(get_current_user)):
    return AccountUser(id=user["id"], email=user.get("email", ""))


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(payload: ForgotPasswordRequest, request: Request, client: Client = Depends(get_supabase_service)):
    service = LocalAuthService(client)
    account = service.get_by_email(str(payload.email))
    if not account:
        return ForgotPasswordResponse(message="If an account exists, reset instructions are ready.")
    token = service.create_reset_token(account["id"])
    frontend_origin = request.headers.get("origin") or settings.FRONTEND_URL
    reset_url = f"{frontend_origin.rstrip('/')}/reset-password?token={token}"
    try:
        if send_reset_email(account["email"], reset_url):
            return ForgotPasswordResponse(message="A secure reset link has been sent.")
    except Exception:
        pass
    return ForgotPasswordResponse(
        message="Email delivery is not configured. Continue with the secure reset link below.",
        reset_token=token,
    )


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, client: Client = Depends(get_supabase_service)):
    if not LocalAuthService(client).reset_password(payload.token, payload.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This reset link is invalid or has expired.")
    return {"message": "Password updated successfully."}
