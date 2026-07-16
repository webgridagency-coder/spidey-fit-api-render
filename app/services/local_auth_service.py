"""Ojas-owned email/password authentication backed by database tables."""

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import uuid4

from jose import jwt
from passlib.context import CryptContext
from supabase import Client

from app.config import settings


password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class LocalAuthService:
    def __init__(self, client: Client):
        self.client = client

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def hash_password(password: str) -> str:
        return password_context.hash(password)

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        return password_context.verify(password, password_hash)

    @staticmethod
    def create_access_token(account_id: str, email: str) -> str:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=settings.OJAS_ACCESS_TOKEN_EXPIRE_MINUTES)
        return jwt.encode(
            {
                "sub": account_id,
                "email": email,
                "iss": "ojas-ai",
                "iat": int(now.timestamp()),
                "exp": int(expires.timestamp()),
            },
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )

    def get_by_email(self, email: str):
        response = (
            self.client.table("ojas_accounts")
            .select("id,email,password_hash,is_active")
            .eq("email", self.normalize_email(email))
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_by_id(self, account_id: str):
        response = (
            self.client.table("ojas_accounts")
            .select("id,email,is_active")
            .eq("id", account_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def create_account(self, email: str, password: str):
        normalized = self.normalize_email(email)
        if self.get_by_email(normalized):
            raise ValueError("An account with this email already exists.")
        account = {
            "id": str(uuid4()),
            "email": normalized,
            "password_hash": self.hash_password(password),
            "is_active": True,
        }
        response = self.client.table("ojas_accounts").insert(account).execute()
        return response.data[0]

    def authenticate(self, email: str, password: str):
        account = self.get_by_email(email)
        if not account or not account.get("is_active"):
            return None
        if not self.verify_password(password, account["password_hash"]):
            return None
        return account

    def create_reset_token(self, account_id: str):
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        self.client.table("ojas_password_reset_tokens").insert(
            {
                "account_id": account_id,
                "token_hash": token_hash,
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            }
        ).execute()
        return raw_token

    def reset_password(self, raw_token: str, password: str) -> bool:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        response = (
            self.client.table("ojas_password_reset_tokens")
            .select("id,account_id,expires_at,used_at")
            .eq("token_hash", token_hash)
            .limit(1)
            .execute()
        )
        if not response.data:
            return False
        record = response.data[0]
        expires_at = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        if record.get("used_at") or expires_at <= datetime.now(timezone.utc):
            return False
        self.client.table("ojas_accounts").update(
            {"password_hash": self.hash_password(password)}
        ).eq("id", record["account_id"]).execute()
        self.client.table("ojas_password_reset_tokens").update(
            {"used_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", record["id"]).execute()
        return True
