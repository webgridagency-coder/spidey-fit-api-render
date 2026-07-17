"""
Trainer Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class TrainerConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=1200)


class TrainerQuotaResponse(BaseModel):
    """Schema for trainer quota response"""
    messages_used: int = Field(..., ge=0, description="Number of messages used today")
    messages_remaining: Optional[int] = Field(..., ge=0, description="Remaining allowance; null means unlimited")
    plan: Literal["base", "flow", "orbit"] = "base"
    period: Literal["day", "month", "unlimited"] = "day"
    limit: Optional[int] = Field(default=5, ge=1)

    class Config:
        json_schema_extra = {
            "example": {
                "messages_used": 3,
                "messages_remaining": 2
            }
        }


class TrainerUseResponse(BaseModel):
    """Schema for trainer use response"""
    success: bool
    messages_used: int
    messages_remaining: Optional[int]
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "messages_used": 4,
                "messages_remaining": 1,
                "message": "Message quota incremented"
            }
        }


class TrainerChatRequest(BaseModel):
    """Schema for trainer chat request"""
    message: str = Field(..., min_length=1, max_length=500, description="User's message to the AI trainer")
    history: List[TrainerConversationMessage] = Field(default_factory=list, max_length=10)

    class Config:
        json_schema_extra = {
            "example": {
                "message": "What's the best workout for fat loss?"
            }
        }


class TrainerChatResponse(BaseModel):
    """Schema for trainer chat response"""
    reply: str = Field(..., description="AI trainer's response")
    messages_used: int = Field(..., ge=0, description="Total messages used today")
    messages_remaining: Optional[int] = Field(..., ge=0, description="Remaining allowance; null means unlimited")
    plan: Literal["base", "flow", "orbit"] = "base"
    period: Literal["day", "month", "unlimited"] = "day"
    request_id: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "reply": "For fat loss, combine HIIT cardio 3x/week with strength training. Focus on compound movements: squats, deadlifts, push-ups. Keep workouts 30-45 mins. Diet matters most—eat in a calorie deficit.",
                "messages_used": 4,
                "messages_remaining": 1
            }
        }
