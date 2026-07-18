"""
Food API Routes - Gemini Flash powered nutrition estimation
Handles text and image-based food tracking with credit system and persistence
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging

from app.services.food_ai_service import FoodAIService
from app.services.credit_service import CreditService
from app.services.food_entry_service import FoodEntryService
from app.dependencies import get_current_user
from app.database import get_supabase_service  # Use service key to bypass RLS
from supabase import Client

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class FoodEstimateTextRequest(BaseModel):
    """Request model for text-based food estimation"""
    meal_type: str = Field(..., description="breakfast, lunch, dinner, or snacks")
    description: str = Field(..., min_length=3, description="Description of the food")


class DailyNutritionTotals(BaseModel):
    """Daily nutrition totals"""
    calories: float
    protein: float
    carbs: float
    fats: float
    fiber: float


class FoodEstimateResponse(BaseModel):
    """Response model for food estimation"""
    calories: float = Field(..., description="Estimated calories")
    protein: float = Field(..., description="Estimated protein in grams")
    carbs: float = Field(..., description="Estimated carbs in grams")
    fats: float = Field(..., description="Estimated fats in grams")
    confidence_note: str = Field(..., description="Confidence note about the estimation")
    remaining_credits: int = Field(..., description="AI credits remaining today")
    daily_nutrition_totals: DailyNutritionTotals = Field(..., description="Updated daily nutrition totals")


class TodayStatusResponse(BaseModel):
    """Response model for today's status"""
    remaining_credits: int
    daily_nutrition_totals: DailyNutritionTotals
    food_entries: List[Dict[str, Any]]


class FoodPreviewResponse(BaseModel):
    calories: float
    protein: float
    carbs: float
    fats: float
    confidence_note: str
    remaining_credits: int
    meal_type: str
    description: str
    source: str


class FoodConfirmRequest(BaseModel):
    meal_type: str
    description: str = Field(..., min_length=2, max_length=500)
    calories: float = Field(..., ge=0, le=10000)
    protein: float = Field(..., ge=0, le=1000)
    carbs: float = Field(..., ge=0, le=2000)
    fats: float = Field(..., ge=0, le=1000)
    fiber: float = Field(default=0, ge=0, le=500)
    confidence_note: str = Field(default="User reviewed AI estimate", max_length=1000)
    source: str = Field(default="ai_image", pattern="^(ai_text|ai_image|manual)$")


@router.post("/estimate/text", response_model=FoodEstimateResponse, status_code=status.HTTP_200_OK)
async def estimate_food_from_text(
    request: FoodEstimateTextRequest,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_service)
):
    """
    Estimate nutrition from text description
    
    - **meal_type**: Type of meal (breakfast, lunch, dinner, snacks)
    - **description**: Text description of the food
    
    Returns estimated calories, protein, carbs, fats, and confidence note
    
    **Credits**: Consumes 1 AI credit per request
    **Persistence**: Saves food entry to database
    **Response**: Includes remaining credits and updated daily nutrition totals
    """
    try:
        user_id = user.get('id')
        logger.info(f"Text estimation request from user {user_id}: {request.description[:50]}")
        
        # Initialize services
        credit_service = CreditService(supabase)
        food_entry_service = FoodEntryService(supabase)
        
        # Check AI credits before processing
        remaining_credits = await credit_service.check_remaining_credits(user_id)
        if remaining_credits <= 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Daily AI limit reached. You have 0 AI estimates left today."
            )
        
        # Perform AI estimation
        ai_service = FoodAIService()
        result = await ai_service.estimate_from_text(request.description)
        
        # Save food entry to database
        await food_entry_service.save_food_entry(
            user_id=user_id,
            meal_type=request.meal_type,
            calories=result['calories'],
            protein=result['protein'],
            carbs=result['carbs'],
            fats=result['fats'],
            fiber=0.0,  # Gemini doesn't estimate fiber yet
            source='ai_text',
            confidence_note=result['confidence_note'],
            description=request.description
        )
        
        # Consume credit after successful estimation
        credit_info = await credit_service.consume_credit(user_id)
        
        # Get updated daily nutrition totals
        daily_totals = await food_entry_service.get_daily_nutrition_totals(user_id)
        
        logger.info(f"Successfully processed text estimation for user {user_id}. Credits remaining: {credit_info['remaining_credits']}")
        
        return FoodEstimateResponse(
            calories=result['calories'],
            protein=result['protein'],
            carbs=result['carbs'],
            fats=result['fats'],
            confidence_note=result['confidence_note'],
            remaining_credits=credit_info['remaining_credits'],
            daily_nutrition_totals=DailyNutritionTotals(**daily_totals)
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error in text estimation: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in text estimation: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis temporarily unavailable"
        )


@router.post("/estimate/image", response_model=FoodEstimateResponse, status_code=status.HTTP_200_OK)
async def estimate_food_from_image(
    image: UploadFile = File(..., description="Food image"),
    meal_type: str = Form(..., description="breakfast, lunch, dinner, or snacks"),
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_service)
):
    """
    Estimate nutrition from food image
    
    - **image**: Image file of the food (JPEG, PNG)
    - **meal_type**: Type of meal (breakfast, lunch, dinner, snacks)
    
    Returns estimated calories, protein, carbs, fats, and confidence note
    
    **Credits**: Consumes 1 AI credit per request
    **Persistence**: Saves food entry to database
    **Response**: Includes remaining credits and updated daily nutrition totals
    """
    try:
        user_id = user.get('id')
        logger.info(f"Image estimation request from user {user_id}")
        
        # Validate meal type
        valid_meal_types = ["breakfast", "lunch", "dinner", "snacks"]
        if meal_type not in valid_meal_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid meal_type. Must be one of: {', '.join(valid_meal_types)}"
            )
        
        # Validate image file
        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an image (JPEG, PNG, etc.)"
            )
        
        # Read image bytes
        image_bytes = await image.read()
        
        # Validate image size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if len(image_bytes) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Image too large. Maximum size is 10MB"
            )
        
        # Initialize services
        credit_service = CreditService(supabase)
        food_entry_service = FoodEntryService(supabase)
        
        # Check AI credits before processing
        remaining_credits = await credit_service.check_remaining_credits(user_id)
        if remaining_credits <= 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Daily AI limit reached. You have 0 AI estimates left today."
            )
        
        # Perform AI estimation
        ai_service = FoodAIService()
        result = await ai_service.estimate_from_image(image_bytes, image.content_type)
        
        # Save food entry to database
        await food_entry_service.save_food_entry(
            user_id=user_id,
            meal_type=meal_type,
            calories=result['calories'],
            protein=result['protein'],
            carbs=result['carbs'],
            fats=result['fats'],
            fiber=0.0,  # Gemini doesn't estimate fiber yet
            source='ai_image',
            confidence_note=result['confidence_note'],
            description=result.get("food_description") or f"Food photo upload - {image.filename}"
        )
        
        # Consume credit after successful estimation
        credit_info = await credit_service.consume_credit(user_id)
        
        # Get updated daily nutrition totals
        daily_totals = await food_entry_service.get_daily_nutrition_totals(user_id)
        
        logger.info(f"Successfully processed image estimation for user {user_id}. Credits remaining: {credit_info['remaining_credits']}")
        
        return FoodEstimateResponse(
            calories=result['calories'],
            protein=result['protein'],
            carbs=result['carbs'],
            fats=result['fats'],
            confidence_note=result['confidence_note'],
            remaining_credits=credit_info['remaining_credits'],
            daily_nutrition_totals=DailyNutritionTotals(**daily_totals)
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error in image estimation: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in image estimation: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis temporarily unavailable"
        )


@router.post("/estimate/image/preview", response_model=FoodPreviewResponse)
async def preview_food_from_image(
    image: UploadFile = File(...),
    meal_type: str = Form(...),
    portion_hint: str = Form(default=""),
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_service),
):
    """Analyze a photo without saving it; the user confirms and edits the estimate next."""
    if meal_type not in {"breakfast", "lunch", "dinner", "snacks"}:
        raise HTTPException(status_code=400, detail="Invalid meal type")
    if not image.content_type or image.content_type not in {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}:
        raise HTTPException(status_code=400, detail="Use a JPEG, PNG, WebP or HEIC food image")
    image_bytes = await image.read()
    if not image_bytes or len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be between 1 byte and 10MB")
    credit_service = CreditService(supabase)
    if await credit_service.check_remaining_credits(user["id"]) <= 0:
        raise HTTPException(status_code=402, detail="Daily AI estimate allowance reached")
    description_hint = portion_hint.strip()[:240]
    try:
        result = await FoodAIService().estimate_from_image(image_bytes, image.content_type, description_hint)
    except Exception as exc:
        logger.warning("Food photo preview failed for user %s: %s", user["id"][:8], type(exc).__name__)
        raise HTTPException(status_code=503, detail="Photo analysis is taking longer than expected. Try again with a clear, well-lit image.") from exc
    credit_info = await credit_service.consume_credit(user["id"])
    detected_food = str(result.get("food_description") or "").strip()
    if description_hint and detected_food:
        reviewed_description = f"{detected_food} · Portion note: {description_hint}"
    else:
        reviewed_description = detected_food or description_hint or f"Food photo · {image.filename or 'meal'}"
    return FoodPreviewResponse(
        **result,
        remaining_credits=credit_info["remaining_credits"],
        meal_type=meal_type,
        description=reviewed_description[:500],
        source="ai_image",
    )


@router.post("/entries/confirm", response_model=TodayStatusResponse, status_code=status.HTTP_201_CREATED)
async def confirm_food_entry(
    request: FoodConfirmRequest,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_service),
):
    """Save user-reviewed AI values or a manual meal entry."""
    if request.meal_type not in {"breakfast", "lunch", "dinner", "snacks"}:
        raise HTTPException(status_code=400, detail="Invalid meal type")
    service = FoodEntryService(supabase)
    await service.save_food_entry(
        user_id=user["id"], meal_type=request.meal_type, calories=request.calories,
        protein=request.protein, carbs=request.carbs, fats=request.fats, fiber=request.fiber,
        source=request.source, confidence_note=request.confidence_note, description=request.description,
    )
    totals = await service.get_daily_nutrition_totals(user["id"])
    entries = await service.get_today_entries(user["id"])
    credits = await CreditService(supabase).check_remaining_credits(user["id"])
    return TodayStatusResponse(remaining_credits=credits, daily_nutrition_totals=DailyNutritionTotals(**totals), food_entries=entries)


@router.put("/entries/{entry_id}", response_model=TodayStatusResponse)
async def update_food_entry(
    entry_id: str,
    request: FoodConfirmRequest,
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_service),
):
    existing = supabase.table("food_entries").select("id").eq("id", entry_id).eq("user_id", user["id"]).limit(1).execute().data
    if not existing:
        raise HTTPException(status_code=404, detail="Meal entry not found")
    supabase.table("food_entries").update({
        "meal_type": request.meal_type, "description": request.description,
        "calories": request.calories, "protein": request.protein, "carbs": request.carbs,
        "fats": request.fats, "fiber": request.fiber, "confidence_note": request.confidence_note,
    }).eq("id", entry_id).eq("user_id", user["id"]).execute()
    service = FoodEntryService(supabase)
    totals = await service.get_daily_nutrition_totals(user["id"])
    entries = await service.get_today_entries(user["id"])
    credits = await CreditService(supabase).check_remaining_credits(user["id"])
    return TodayStatusResponse(remaining_credits=credits, daily_nutrition_totals=DailyNutritionTotals(**totals), food_entries=entries)


@router.get("/today", response_model=TodayStatusResponse, status_code=status.HTTP_200_OK)
async def get_today_status(
    user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_service)
):
    """
    Get current status for today
    
    Returns:
    - remaining_credits: AI estimates left for today
    - daily_nutrition_totals: Aggregated nutrition for all meals today
    - food_entries: List of all food entries logged today
    
    **Use this endpoint on page load to hydrate UI state**
    """
    try:
        user_id = user.get('id')
        logger.info(f"Getting today's status for user {user_id}")
        
        # Initialize services
        credit_service = CreditService(supabase)
        food_entry_service = FoodEntryService(supabase)
        
        # Get credit info
        credit_info = await credit_service.get_or_create_daily_credits(user_id)
        
        # Get daily nutrition totals
        daily_totals = await food_entry_service.get_daily_nutrition_totals(user_id)
        
        # Get all food entries for today
        food_entries = await food_entry_service.get_today_entries(user_id)
        
        return TodayStatusResponse(
            remaining_credits=credit_info['remaining_credits'],
            daily_nutrition_totals=DailyNutritionTotals(**daily_totals),
            food_entries=food_entries
        )
        
    except Exception as e:
        logger.error(f"Error getting today's status for user {user_id}: {e}")
        # Return safe defaults on error
        return TodayStatusResponse(
            remaining_credits=3,
            daily_nutrition_totals=DailyNutritionTotals(
                calories=0, protein=0, carbs=0, fats=0, fiber=0
            ),
            food_entries=[]
        )


# Health check endpoint for food AI service
@router.get("/health")
async def food_ai_health():
    """
    Check if Food AI service is configured and ready
    """
    try:
        service = FoodAIService()
        return {
            "status": "healthy",
            "model": service.model,
            "configured": True
        }
    except ValueError as e:
        return {
            "status": "not_configured",
            "model": None,
            "configured": False,
            "error": str(e)
        }
