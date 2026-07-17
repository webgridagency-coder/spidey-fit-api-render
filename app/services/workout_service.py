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

    async def get_recent_workouts(self, user_id: str, limit: int = 7) -> list[Dict[str, Any]]:
        """
        Get recent workouts for a user, newest first.
        """
        response = self.client.table("workouts").select("*").eq(
            "user_id", user_id
        ).order("date", desc=True).limit(limit).execute()

        return response.data or []
    
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
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
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

    async def complete_today_workout(self, user_id: str) -> Dict[str, Any]:
        """Persist explicit workout completion so Ojas can use it as evidence."""
        workout = await self.get_today_workout(user_id)
        if not workout:
            raise Exception("No saved workout found for today")

        completed_at = datetime.utcnow().isoformat()
        response = self.client.table("workouts").update({
            "completed_at": completed_at
        }).eq("id", workout["id"]).eq("user_id", user_id).execute()
        if response.data:
            return response.data[0]

        # Some PostgREST configurations do not return the updated row. The
        # write still succeeded, so return the known workout with its new state.
        return {**workout, "completed_at": completed_at}
