"""
Workout API routes
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_supabase_service
from app.dependencies import get_current_user
from app.schemas.workout import FormSessionCreate, FormSessionResponse, WorkoutCreate, WorkoutResponse
from app.services.workout_service import WorkoutService
from supabase import Client


router = APIRouter()

SUPPORTED_FORM_EXERCISES = {
    "Push-ups", "Squats", "Lunges", "Shoulder Press", "Bicep Curls", "Plank",
}


@router.post("/form-sessions", response_model=FormSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_form_session(
    session: FormSessionCreate,
    user: dict = Depends(get_current_user),
    client: Client = Depends(get_supabase_service),
):
    if session.exercise_name not in SUPPORTED_FORM_EXERCISES:
        raise HTTPException(status_code=422, detail="This movement is not supported by the calibrated form tracker")
    payload = {"user_id": user["id"], **session.model_dump()}
    response = client.table("form_sessions").insert(payload).execute()
    if not response.data:
        raise HTTPException(status_code=503, detail="Form-session sync is temporarily unavailable")
    return response.data[0]


@router.get("/form-sessions/recent", response_model=list[FormSessionResponse])
async def get_recent_form_sessions(
    user: dict = Depends(get_current_user),
    client: Client = Depends(get_supabase_service),
):
    response = client.table("form_sessions").select("*").eq("user_id", user["id"]).order("created_at", desc=True).limit(30).execute()
    return response.data or []


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


@router.get("/recent", response_model=list[WorkoutResponse])
async def get_recent_workouts(
    user: dict = Depends(get_current_user),
    client: Client = Depends(get_supabase_service),
):
    """
    Get recent workout history for the authenticated user.
    """
    service = WorkoutService(client)

    try:
        return await service.get_recent_workouts(user["id"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch workout history"
        )


@router.post("/complete-today", response_model=WorkoutResponse)
async def complete_today_workout(
    user: dict = Depends(get_current_user),
    client: Client = Depends(get_supabase_service),
):
    """Mark today's saved workout completed using a server timestamp."""
    service = WorkoutService(client)
    try:
        return await service.complete_today_workout(user["id"])
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
