"""
User Profile Schemas
Pydantic models for user fitness profile data
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class Gender(str, Enum):
    """Gender options"""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class Goal(str, Enum):
    """Fitness goal options"""
    FAT_LOSS = "fat_loss"
    MUSCLE_GAIN = "muscle_gain"
    RECOMPOSITION = "recomposition"


class ActivityLevel(str, Enum):
    """Physical activity level"""
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"


class ExperienceLevel(str, Enum):
    """Training experience level"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class DietPreference(str, Enum):
    """Dietary preference"""
    VEG = "veg"
    NON_VEG = "non_veg"
    MIXED = "mixed"
    INDIAN = "indian"
    ANY = "any"


class ProfileCreate(BaseModel):
    """Schema for creating/updating user profile"""
    height_cm: Optional[int] = Field(None, gt=0, le=300, description="Height in centimeters")
    weight_kg: Optional[float] = Field(None, gt=0, le=500, description="Weight in kilograms")
    body_fat_percentage: Optional[float] = Field(None, gt=0, le=100, description="Body fat percentage")
    age: Optional[int] = Field(None, gt=0, le=150, description="Age in years")
    gender: Optional[Gender] = Field(None, description="Gender")
    goal: Optional[Goal] = Field(None, description="Fitness goal")
    activity_level: Optional[ActivityLevel] = Field(None, description="Daily activity level")
    experience_level: Optional[ExperienceLevel] = Field(None, description="Training experience")
    injuries: Optional[str] = Field(None, max_length=1000, description="Current injuries or limitations")
    diet_preference: Optional[DietPreference] = Field(None, description="Dietary preference")
    cuisine_preference: Optional[str] = Field(None, max_length=50, description="Cuisine preference for onboarding")
    challenges: Optional[list[str]] = Field(None, description="Selected challenges")
    onboarding_completed: Optional[bool] = Field(None, description="Whether onboarding is completed")

    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "height_cm": 175,
                "weight_kg": 75,
                "body_fat_percentage": 20.0,
                "age": 28,
                "gender": "male",
                "goal": "muscle_gain",
                "activity_level": "moderate",
                "experience_level": "intermediate",
                "injuries": "Previous lower back injury - avoid heavy deadlifts",
                "diet_preference": "non_veg",
                "cuisine_preference": "indian",
                "challenges": ["train_4_days", "protein_consistency"],
                "onboarding_completed": True
            }
        }


class ProfileResponse(BaseModel):
    """Schema for profile response"""
    user_id: str
    height_cm: Optional[int] = None
    weight_kg: Optional[float] = None
    body_fat_percentage: Optional[float] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    goal: Optional[str] = None
    activity_level: Optional[str] = None
    experience_level: Optional[str] = None
    injuries: Optional[str] = None
    diet_preference: Optional[str] = None
    cuisine_preference: Optional[str] = None
    challenges: Optional[list[str]] = None
    onboarding_completed: Optional[bool] = None
    challenge_start_date: Optional[str] = None
    challenge_duration_days: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "height_cm": 175,
                "weight_kg": 75,
                "age": 28,
                "gender": "male",
                "goal": "muscle_gain",
                "activity_level": "moderate",
                "experience_level": "intermediate",
                "injuries": "Previous lower back injury - avoid heavy deadlifts",
                "diet_preference": "non_veg",
                "created_at": "2025-12-31T10:00:00Z",
                "updated_at": "2025-12-31T10:00:00Z"
            }
        }
