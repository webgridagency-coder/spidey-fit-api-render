"""
Dependency injection functions for FastAPI routes.
Provides authentication, database access, and other shared dependencies.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from supabase import Client

from app.config import settings
from app.database import get_supabase_service


# Security scheme for JWT Bearer tokens
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    supabase: Client = Depends(get_supabase_service)
) -> dict:
    """
    Validate JWT token and return current user.
    
    Args:
        credentials: HTTP Bearer token from request header
        supabase: Supabase client instance
    
    Returns:
        User dictionary with user information
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials
    
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        if payload.get("iss") == "ojas-ai" and payload.get("sub"):
            account = (
                supabase.table("ojas_accounts")
                .select("id,email,is_active")
                .eq("id", payload["sub"])
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            if account.data:
                return {"id": account.data[0]["id"], "email": account.data[0]["email"], "provider": "ojas"}
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session account no longer exists",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        pass

    try:
        # Google accounts continue to use their existing Supabase OAuth session.
        user = supabase.auth.get_user(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user.user.model_dump()
    
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Verify user is active (not banned/disabled).
    
    Args:
        current_user: Current authenticated user
    
    Returns:
        Active user dictionary
    
    Raises:
        HTTPException: If user is inactive
    """
    # Add custom user validation logic here if needed
    # For example, check if user is banned, email verified, etc.
    
    return current_user


async def get_current_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Require an authenticated account on the server-side admin allowlist."""
    email = str(current_user.get("email") or "").strip().lower()
    if not settings.admin_emails_list:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured.",
        )
    if not email or email not in settings.admin_emails_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account does not have admin access.",
        )
    return {**current_user, "email": email, "admin_role": "owner"}


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    supabase: Client = Depends(get_supabase_service)
) -> Optional[dict]:
    """
    Get current user if token is provided, otherwise return None.
    Useful for endpoints that work for both authenticated and anonymous users.
    
    Args:
        credentials: Optional HTTP Bearer token
        supabase: Supabase client instance
    
    Returns:
        User dictionary or None
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, supabase)
    except HTTPException:
        return None
