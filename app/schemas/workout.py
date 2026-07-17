"""
Workout Pydantic schemas for request/response validation
"""

from datetime import date, datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class WorkoutCreate(BaseModel):
    """Schema for creating a workout"""
    muscle: str = Field(..., min_length=1, max_length=50, description="Muscle group name")
    exercises: List[str] = Field(..., min_items=1, max_items=10, description="List of exercise names")

    class Config:
        json_schema_extra = {
            "example": {
                "muscle": "Chest",
                "exercises": [
                    "Bench Press",
                    "Incline Dumbbell Press",
                    "Cable Flyes",
                    "Push-ups"
                ]
            }
        }


class WorkoutResponse(BaseModel):
    """Schema for workout response"""
    id: str
    user_id: str
    date: date
    muscle: str
    exercises: List[str]
    created_at: str
    completed_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "date": "2025-12-31",
                "muscle": "Chest",
                "exercises": ["Bench Press", "Incline Dumbbell Press", "Cable Flyes", "Push-ups"],
                "created_at": "2025-12-31T10:30:00Z"
            }
        }


class FormSessionCreate(BaseModel):
    exercise_name: str = Field(..., min_length=2, max_length=100)
    reps: int = Field(..., ge=1, le=1000)
    sets: int = Field(..., ge=0, le=100)
    duration_seconds: int = Field(..., ge=0, le=21600)
    form_score: float = Field(..., ge=0, le=100)
    calories: float = Field(default=0, ge=0, le=5000)
    device_label: Optional[str] = Field(default=None, max_length=120)
    confidence_level: Literal["low", "estimated", "high"] = "estimated"


class FormSessionResponse(FormSessionCreate):
    id: str
    user_id: str
    created_at: datetime
