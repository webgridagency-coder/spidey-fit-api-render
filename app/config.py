"""
Configuration management for Ojas AI API.
Loads environment variables and provides application settings.
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Supabase Configuration
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_KEY: str
    
    # JWT Configuration
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    OJAS_ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    FRONTEND_URL: str = "http://localhost:3000"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    ADMIN_EMAILS: str = ""
    
    # OpenRouter AI Configuration (DeepSeek via OpenRouter)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1/chat/completions"
    OPENROUTER_MODEL: str = "deepseek/deepseek-chat"
    OPENROUTER_TIMEOUT: int = 30
    
    # Gemini Flash AI Configuration (Food Tracking)
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_TIMEOUT: int = 60  # Increased timeout for image processing
    
    # Environment
    ENVIRONMENT: str = "development"
    ALLOW_DEV_AUTH_BYPASS: bool = False
    
    # CORS Configuration
    CORS_ORIGINS: str = "http://localhost:3000"
    
    # API Configuration
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "Ojas AI API"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        origins = [origin.strip().rstrip("/") for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("CORS_ORIGINS cannot include '*' when credentials are enabled")
        return origins

    @property
    def admin_emails_list(self) -> List[str]:
        """Server-side owner allowlist. Empty deliberately means no admin access."""
        return [email.strip().lower() for email in self.ADMIN_EMAILS.split(",") if email.strip()]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# Global settings instance
settings = Settings()
