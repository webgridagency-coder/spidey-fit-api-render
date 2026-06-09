"""
Workout API routes
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_supabase_service
from app.dependencies import get_current_user
from app.schemas.workout import WorkoutCreate, WorkoutResponse
from app.services.workout_service import WorkoutService
from supabase import Client


router = APIRouter()


@router.post("", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def create_workout(
    workout: WorkoutCreate,
    user: dict = Depends(get_current_user),
    client: Client = Depends(get_supabase_service),
):
    """
    Create or update today's workout.
    Only one workout per user per day - overwrites if exists.
    """
    service = WorkoutService(client)
    
    try:
        result = await service.create_or_update_workout(
            user_id=user["id"],
            muscle=workout.muscle,
            exercises=workout.exercises
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save workout"
        )


@router.get("/today", response_model=WorkoutResponse | None)
async def get_today_workout(
    user: dict = Depends(get_current_user),
    client: Client = Depends(get_supabase_service),
):
    """
    Get today's workout for the authenticated user.
    Returns null if no workout exists for today.
    """
    service = WorkoutService(client)
    
    try:
        result = await service.get_today_workout(user["id"])
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch workout"
        )
