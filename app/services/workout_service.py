"""
Workout service layer - handles business logic and database operations
"""

from datetime import date, datetime
from typing import Optional, Dict, Any
from supabase import Client


class WorkoutService:
    """Service for workout-related operations"""
    
    def __init__(self, supabase_client: Client):
        self.client = supabase_client
    
    async def get_today_workout(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get today's workout for a user.
        
        Args:
            user_id: User's UUID
            
        Returns:
            Workout dict or None if not found
        """
        today = date.today().isoformat()
        
        response = self.client.table("workouts").select("*").eq(
            "user_id", user_id
        ).eq("date", today).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        
        return None
    
    async def create_or_update_workout(
        self, 
        user_id: str, 
        muscle: str, 
        exercises: list
    ) -> Dict[str, Any]:
        """
        Create or update today's workout for a user.
        Only one workout per user per day - overwrites if exists.
        
        Args:
            user_id: User's UUID
            muscle: Muscle group name
            exercises: List of exercise names
            
        Returns:
            Created/updated workout dict
        """
        today = date.today().isoformat()
        
        # Check if workout exists today
        existing = await self.get_today_workout(user_id)
        
        workout_data = {
            "user_id": user_id,
            "date": today,
            "muscle": muscle,
            "exercises": exercises,
            "created_at": datetime.utcnow().isoformat()
        }
        
        if existing:
            # Update existing workout
            response = self.client.table("workouts").update(workout_data).eq(
                "id", existing["id"]
            ).execute()
        else:
            # Create new workout
            response = self.client.table("workouts").insert(workout_data).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        
        raise Exception("Failed to save workout")
