"""
Database client initialization for Supabase.
Provides singleton Supabase client instance.
"""

from supabase import create_client, Client
from app.config import settings


class SupabaseClient:
    """Singleton Supabase client wrapper."""
    
    _instance: Client = None
    _service_instance: Client = None
    
    @classmethod
    def get_client(cls) -> Client:
        """
        Get Supabase client instance (anon key).
        Used for client-side operations with RLS enabled.
        """
        if cls._instance is None:
            cls._instance = create_client(
                supabase_url=settings.SUPABASE_URL,
                supabase_key=settings.SUPABASE_KEY
            )
        return cls._instance
    
    @classmethod
    def get_service_client(cls) -> Client:
        """
        Get Supabase service client (service role key).
        Used for server-side operations bypassing RLS.
        """
        if cls._service_instance is None:
            cls._service_instance = create_client(
                supabase_url=settings.SUPABASE_URL,
                supabase_key=settings.SUPABASE_SERVICE_KEY
            )
        return cls._service_instance


# Dependency injection functions
def get_supabase() -> Client:
    """FastAPI dependency to get Supabase client."""
    return SupabaseClient.get_client()


def get_supabase_service() -> Client:
    """FastAPI dependency to get Supabase service client."""
    return SupabaseClient.get_service_client()
