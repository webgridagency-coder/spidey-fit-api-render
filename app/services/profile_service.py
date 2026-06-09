"""
User Profile Service
Business logic for user profile CRUD operations
"""

from typing import Optional
from datetime import datetime
from supabase import Client
from app.schemas.profile import ProfileCreate, ProfileResponse


class ProfileService:
    """Service for managing user profiles"""

    def __init__(self, supabase: Client):
        self.supabase = supabase

    async def get_profile(self, user_id: str) -> Optional[ProfileResponse]:
        """
        Get user profile by user_id
        
        Args:
            user_id: User's unique identifier
            
        Returns:
            ProfileResponse or None if not found
        """
        response = self.supabase.table("user_profile").select("*").eq("user_id", user_id).execute()
        
        if not response.data or len(response.data) == 0:
            return None
            
        profile_data = response.data[0]
        return ProfileResponse(**profile_data)

    async def create_or_update_profile(
        self, 
        user_id: str, 
        profile_data: ProfileCreate
    ) -> ProfileResponse:
        """
        Create or update user profile (upsert)
        
        Args:
            user_id: User's unique identifier
            profile_data: Profile data to save
            
        Returns:
            Created/updated ProfileResponse
        """
        # Prepare data for insert/update
        data = {
            "user_id": user_id,
            **profile_data.model_dump(exclude_none=True),  # Only include non-None values
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Upsert: Insert if not exists, update if exists
        response = self.supabase.table("user_profile").upsert(
            data,
            on_conflict="user_id"
        ).execute()
        
        if not response.data or len(response.data) == 0:
            raise Exception("Failed to create/update profile")
        
        return ProfileResponse(**response.data[0])

    async def delete_profile(self, user_id: str) -> bool:
        """
        Delete user profile
        
        Args:
            user_id: User's unique identifier
            
        Returns:
            True if deleted successfully
        """
        response = self.supabase.table("user_profile").delete().eq("user_id", user_id).execute()
        return True
