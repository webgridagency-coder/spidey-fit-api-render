"""
Trainer service layer - handles message quota business logic
"""

from datetime import date, datetime
from typing import Dict, Any
from supabase import Client


class TrainerService:
    """Service for trainer message quota operations"""
    
    MAX_MESSAGES_PER_DAY = 5
    
    def __init__(self, supabase_client: Client):
        self.client = supabase_client
    
    async def get_or_create_usage(self, user_id: str) -> Dict[str, Any]:
        """
        Get today's usage record for a user. Create if doesn't exist.
        
        Args:
            user_id: User's UUID
            
        Returns:
            Usage record dict
            
        Raises:
            Exception: If database operation fails
        """
        today = date.today().isoformat()
        
        try:
            # Try to get existing record
            response = self.client.table("trainer_usage").select("*").eq(
                "user_id", user_id
            ).eq("date", today).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            
            # Create new record for today
            new_record = {
                "user_id": user_id,
                "date": today,
                "messages_used": 0,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            create_response = self.client.table("trainer_usage").insert(new_record).execute()
            
            if create_response.data and len(create_response.data) > 0:
                return create_response.data[0]
            
            raise Exception("Failed to create usage record")
            
        except Exception as e:
            # Check for specific Supabase errors
            error_msg = str(e)
            if "PGRST204" in error_msg or "trainer_usage" in error_msg:
                raise Exception("trainer_usage table not found - run TRAINER_USAGE_FIX.sql migration")
            raise Exception(f"Database error: {error_msg}")
    
    async def get_quota(self, user_id: str) -> Dict[str, int]:
        """
        Get current message quota for user.
        
        Args:
            user_id: User's UUID
            
        Returns:
            Dict with messages_used and messages_remaining
        """
        usage = await self.get_or_create_usage(user_id)
        messages_used = usage.get("messages_used", 0)
        messages_remaining = max(0, self.MAX_MESSAGES_PER_DAY - messages_used)
        
        return {
            "messages_used": messages_used,
            "messages_remaining": messages_remaining
        }
    
    async def increment_usage(self, user_id: str) -> Dict[str, Any]:
        """
        Increment message usage by 1. Enforce daily limit.
        
        Args:
            user_id: User's UUID
            
        Returns:
            Updated usage info
            
        Raises:
            Exception: If daily limit exceeded
        """
        usage = await self.get_or_create_usage(user_id)
        messages_used = usage.get("messages_used", 0)
        
        # Enforce limit
        if messages_used >= self.MAX_MESSAGES_PER_DAY:
            raise Exception("Daily message limit exceeded")
        
        # Increment
        new_count = messages_used + 1
        
        update_data = {
            "messages_used": new_count,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        response = self.client.table("trainer_usage").update(update_data).eq(
            "user_id", user_id
        ).eq("date", usage["date"]).execute()
        
        if response.data and len(response.data) > 0:
            return {
                "messages_used": new_count,
                "messages_remaining": self.MAX_MESSAGES_PER_DAY - new_count
            }
        
        raise Exception("Failed to update usage")
    
    # ==========================================
    # PREPARATION FOR AI PERSONALIZATION
    # ==========================================
    # NOTE: This method is a placeholder for future implementation
    # When AI personalization is implemented, this will accept user
    # profile data and inject it into the AI system prompt
    
    async def get_personalized_context(self, user_id: str) -> Dict[str, Any]:
        """
        PLACEHOLDER: Get user profile context for AI personalization.
        
        Future implementation will:
        - Fetch user profile (fitness_goal, experience_level, etc.)
        - Fetch recent workouts
        - Format data for AI system prompt injection
        
        Args:
            user_id: User's UUID
            
        Returns:
            Dict with user context for AI personalization
            
        NOTE: Do NOT implement this yet. This is prep for next step.
        """
        # TODO: Implement in next phase when adding AI personalization
        return {
            "user_id": user_id,
            "profile_available": False,
            "personalization_ready": False
        }
