"""
Trainer service layer - handles message quota business logic
"""

from datetime import date, datetime
from calendar import monthrange
from typing import Dict, Any
from supabase import Client


class TrainerService:
    """Service for trainer message quota operations"""
    
    PLAN_RULES = {
        "base": {"limit": 5, "period": "day"},
        "flow": {"limit": 50, "period": "month"},
        "orbit": {"limit": None, "period": "unlimited"},
    }
    
    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    def get_plan(self, user_id: str) -> str:
        response = self.client.table("ojas_accounts").select("plan").eq("id", user_id).limit(1).execute()
        plan = (response.data or [{}])[0].get("plan", "base")
        return plan if plan in self.PLAN_RULES else "base"

    def get_period_usage(self, user_id: str, plan: str) -> int:
        rule = self.PLAN_RULES[plan]
        if rule["period"] == "day":
            start = end = date.today().isoformat()
        else:
            today = date.today()
            start = today.replace(day=1).isoformat()
            end = today.replace(day=monthrange(today.year, today.month)[1]).isoformat()
        response = self.client.table("trainer_usage").select("messages_used").eq("user_id", user_id).gte("date", start).lte("date", end).execute()
        return sum(int(row.get("messages_used", 0) or 0) for row in (response.data or []))
    
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
        plan = self.get_plan(user_id)
        rule = self.PLAN_RULES[plan]
        # Base is a daily plan, so today's already-loaded record is the full
        # period total. Avoid another database round trip on every page load.
        messages_used = (
            int(usage.get("messages_used", 0) or 0)
            if rule["period"] == "day"
            else self.get_period_usage(user_id, plan)
        )
        messages_remaining = None if rule["limit"] is None else max(0, rule["limit"] - messages_used)
        
        return {
            "messages_used": messages_used,
            "messages_remaining": messages_remaining,
            "plan": plan,
            "period": rule["period"],
            "limit": rule["limit"],
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
        plan = self.get_plan(user_id)
        rule = self.PLAN_RULES[plan]
        messages_used = (
            int(usage.get("messages_used", 0) or 0)
            if rule["period"] == "day"
            else self.get_period_usage(user_id, plan)
        )
        
        # Enforce limit
        if rule["limit"] is not None and messages_used >= rule["limit"]:
            raise Exception("Daily message limit exceeded")
        
        # Increment
        daily_count = int(usage.get("messages_used", 0) or 0) + 1
        new_count = messages_used + 1
        
        update_data = {
            "messages_used": daily_count,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        response = self.client.table("trainer_usage").update(update_data).eq(
            "user_id", user_id
        ).eq("date", usage["date"]).execute()
        
        if response.data and len(response.data) > 0:
            return {
                "messages_used": new_count,
                "messages_remaining": None if rule["limit"] is None else max(0, rule["limit"] - new_count),
                "plan": plan,
                "period": rule["period"],
                "limit": rule["limit"],
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
