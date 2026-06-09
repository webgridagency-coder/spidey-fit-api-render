"""
Food Estimation Service - AI-powered food calorie estimation with daily limits
Implements: Max 3 text estimates/day, 3 image estimates/day
Principle: Trust > Accuracy
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import date
from supabase import Client

logger = logging.getLogger(__name__)


class FoodEstimationService:
    """
    Handle food estimation requests with daily limits.
    
    Rules (SOURCE DOCUMENT):
    - Max 3 text estimates per day
    - Max 3 image estimates per day
    - Always show: "AI estimate – adjust if needed"
    - Calm refusal when limit reached
    - Daily reset via food_estimates_reset_date
    """
    
    MAX_TEXT_ESTIMATES = 3
    MAX_IMAGE_ESTIMATES = 3
    
    async def check_daily_limit(
        self,
        user_id: str,
        estimate_type: str,
        client: Client
    ) -> Tuple[bool, int, int]:
        """
        Check if user has reached daily estimation limit.
        
        Args:
            user_id: User's UUID
            estimate_type: "text" or "image"
            client: Supabase client (service_role)
            
        Returns:
            Tuple of (can_estimate: bool, current_count: int, max_count: int)
        """
        try:
            # Fetch current counters
            response = client.table("user_profile").select(
                "food_text_estimates_today, food_image_estimates_today, food_estimates_reset_date"
            ).eq("user_id", user_id).execute()
            
            if not response.data or len(response.data) == 0:
                logger.warning(f"No profile found for user {user_id[:8]}...")
                return (False, 0, 0)
            
            profile = response.data[0]
            today = date.today()
            reset_date = profile.get("food_estimates_reset_date")
            
            # Reset counters if date has changed
            if not reset_date or str(reset_date) != str(today):
                client.table("user_profile").update({
                    "food_text_estimates_today": 0,
                    "food_image_estimates_today": 0,
                    "food_estimates_reset_date": today.isoformat()
                }).eq("user_id", user_id).execute()
                
                logger.info(f"✅ Reset daily food counters for user {user_id[:8]}...")
                return (True, 0, self.MAX_TEXT_ESTIMATES if estimate_type == "text" else self.MAX_IMAGE_ESTIMATES)
            
            # Check limits
            if estimate_type == "text":
                current = profile.get("food_text_estimates_today", 0)
                max_allowed = self.MAX_TEXT_ESTIMATES
            elif estimate_type == "image":
                current = profile.get("food_image_estimates_today", 0)
                max_allowed = self.MAX_IMAGE_ESTIMATES
            else:
                logger.error(f"Invalid estimate_type: {estimate_type}")
                return (False, 0, 0)
            
            can_estimate = current < max_allowed
            return (can_estimate, current, max_allowed)
            
        except Exception as e:
            logger.error(f"❌ Failed to check daily limit: {type(e).__name__}: {str(e)}")
            return (False, 0, 0)
    
    async def increment_counter(
        self,
        user_id: str,
        estimate_type: str,
        client: Client
    ) -> bool:
        """
        Increment the estimation counter after a successful estimate.
        
        Args:
            user_id: User's UUID
            estimate_type: "text" or "image"
            client: Supabase client (service_role)
            
        Returns:
            True if incremented successfully, False otherwise
        """
        try:
            # Fetch current count
            response = client.table("user_profile").select(
                "food_text_estimates_today, food_image_estimates_today"
            ).eq("user_id", user_id).execute()
            
            if not response.data or len(response.data) == 0:
                return False
            
            profile = response.data[0]
            
            if estimate_type == "text":
                new_count = profile.get("food_text_estimates_today", 0) + 1
                update_data = {"food_text_estimates_today": new_count}
            elif estimate_type == "image":
                new_count = profile.get("food_image_estimates_today", 0) + 1
                update_data = {"food_image_estimates_today": new_count}
            else:
                return False
            
            # Update counter
            client.table("user_profile").update(update_data).eq("user_id", user_id).execute()
            logger.info(f"✅ Incremented {estimate_type} counter to {new_count} for user {user_id[:8]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to increment counter: {type(e).__name__}: {str(e)}")
            return False
    
    def format_limit_reached_message(self, estimate_type: str) -> str:
        """
        Generate calm refusal message when limit is reached.
        
        SOURCE DOCUMENT: "Calm refusal + suggest manual logging"
        
        Args:
            estimate_type: "text" or "image"
            
        Returns:
            User-friendly message
        """
        if estimate_type == "text":
            return (
                f"You've used {self.MAX_TEXT_ESTIMATES} AI text estimates today (resets tomorrow). "
                "For now, manually log this meal or use a nutrition app."
            )
        elif estimate_type == "image":
            return (
                f"You've used {self.MAX_IMAGE_ESTIMATES} AI image estimates today (resets tomorrow). "
                "For now, manually log this meal or use a nutrition app."
            )
        else:
            return "Daily estimation limit reached. Please log manually for now."
    
    def format_estimate_confidence_message(self) -> str:
        """
        Return the confidence message to show with all estimates.
        
        SOURCE DOCUMENT: "Always show: 'AI estimate – adjust if needed'"
        
        Returns:
            Confidence message string
        """
        return "AI estimate – adjust if needed"
    
    async def can_estimate_food(
        self,
        user_id: str,
        estimate_type: str,
        client: Client
    ) -> Dict[str, Any]:
        """
        Check if user can request a food estimation.
        
        Args:
            user_id: User's UUID
            estimate_type: "text" or "image"
            client: Supabase client (service_role)
            
        Returns:
            Dictionary with:
            - allowed: bool (can estimate or not)
            - current_count: int
            - max_count: int
            - message: str (error message if not allowed)
        """
        can_estimate, current, max_allowed = await self.check_daily_limit(
            user_id, estimate_type, client
        )
        
        return {
            "allowed": can_estimate,
            "current_count": current,
            "max_count": max_allowed,
            "message": self.format_limit_reached_message(estimate_type) if not can_estimate else None,
            "confidence_message": self.format_estimate_confidence_message()
        }
