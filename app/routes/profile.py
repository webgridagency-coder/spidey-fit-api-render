"""
Profile API routes - user fitness profile management
"""

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client
from typing import Optional

from app.database import get_supabase_service
from app.dependencies import get_current_user
from app.schemas.profile import ProfileCreate, ProfileResponse
from app.services.profile_service import ProfileService


router = APIRouter()


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_profile(
    profile_data: ProfileCreate,
    user: dict = Depends(get_current_user),
    client: Client = Depends(get_supabase_service)
):
    """
    Create or update user fitness profile.
    
    - **goal**: Fitness goal (fat_loss, muscle_gain, recomposition)
    - **activity_level**: Daily activity level (sedentary, light, moderate, heavy)
    - **experience_level**: Training experience (beginner, intermediate, advanced)
    - **height_cm**: Height in centimeters (optional)
    - **weight_kg**: Weight in kilograms (optional)
    - **age**: Age in years (optional)
    - **gender**: Gender (male, female, other) (optional)
    - **injuries**: Current injuries or limitations (optional)
    - **diet_preference**: Dietary preference (veg, non_veg, mixed) (optional)
    
    Returns the created/updated profile.
    """
    service = ProfileService(client)
    
    try:
        profile = await service.create_or_update_profile(
            user_id=user["id"],
            profile_data=profile_data
        )
        return profile
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create/update profile: {str(e)}"
        )


@router.get("/me", response_model=Optional[ProfileResponse])
async def get_my_profile(
    user: dict = Depends(get_current_user),
    client: Client = Depends(get_supabase_service)
):
    """
    Get the authenticated user's fitness profile.
    
    Returns the profile if it exists, or null if no profile has been created yet.
    """
    service = ProfileService(client)
    
    try:
        profile = await service.get_profile(user_id=user["id"])
        return profile
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch profile: {str(e)}"
        )
