"""
Trainer API routes - message quota enforcement and AI chat
"""

import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from supabase import Client

logger = logging.getLogger(__name__)

from app.database import get_supabase
from app.dependencies import get_current_user
from app.schemas.trainer import TrainerQuotaResponse, TrainerUseResponse, TrainerChatRequest, TrainerChatResponse
from app.services.trainer_service import TrainerService
from app.services.ai_trainer_service import AITrainerService
from app.services.profile_extractor_service import ProfileExtractorService


router = APIRouter()


@router.get("/quota", response_model=TrainerQuotaResponse)
async def get_trainer_quota(
    user: dict = Depends(get_current_user),
):
    """
    Get current trainer message quota for the authenticated user.
    Returns messages used and remaining for today.
    """
    # Use service client to bypass RLS (server-side operation)
    from app.database import SupabaseClient
    client = SupabaseClient.get_service_client()
    service = TrainerService(client)
    
    try:
        quota = await service.get_quota(user["id"])
        return quota
    except Exception as e:
        logger.exception("Failed to fetch trainer quota")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch quota"
        )


@router.post("/use", response_model=TrainerUseResponse)
async def use_trainer_message(
    user: dict = Depends(get_current_user),
):
    """
    Increment trainer message usage by 1.
    Enforces daily limit of 5 messages per user.
    Returns HTTP 429 if limit exceeded.
    """
    # Use service client to bypass RLS (server-side operation)
    from app.database import SupabaseClient
    client = SupabaseClient.get_service_client()
    service = TrainerService(client)
    
    try:
        result = await service.increment_usage(user["id"])
        
        return {
            "success": True,
            "messages_used": result["messages_used"],
            "messages_remaining": result["messages_remaining"],
            "message": "Message quota incremented"
        }
        
    except Exception as e:
        error_msg = str(e)
        
        # Daily limit exceeded - return 429
        if "limit exceeded" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Daily message limit exceeded",
                    "messages_used": 5,
                    "messages_remaining": 0
                }
            )
        
        # Other errors - return 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to increment usage: {error_msg}"
        )


@router.post("/chat", response_model=TrainerChatResponse)
async def chat_with_trainer(
    request: TrainerChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Chat with AI trainer (DeepSeek).
    
    Flow:
    1. Check quota
    2. Increment usage (enforces 5/day limit)
    3. Get AI response from DeepSeek
    4. Return response with updated quota
    
    Returns HTTP 429 if daily limit exceeded.
    Returns HTTP 503 if AI service unavailable.
    """
    # Use service client to bypass RLS (server-side operation)
    from app.database import SupabaseClient
    client = SupabaseClient.get_service_client()
    
    trainer_service = TrainerService(client)
    ai_service = AITrainerService()
    
    try:
        # Step 1: Check current quota
        quota = await trainer_service.get_quota(user["id"])
        
        if quota["messages_remaining"] <= 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Daily message limit exceeded",
                    "messages_used": quota["messages_used"],
                    "messages_remaining": 0
                }
            )
        
        # Step 2: Increment usage (this enforces the limit server-side)
        try:
            usage = await trainer_service.increment_usage(user["id"])
        except Exception as e:
            if "limit exceeded" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Daily message limit exceeded",
                        "messages_used": 5,
                        "messages_remaining": 0
                    }
                )
            raise

        extractor_service = ProfileExtractorService()
        fast_profile_data = extractor_service.extract_profile_data_fast(request.message)
        if fast_profile_data:
            await extractor_service.save_profile_data(
                user_id=user["id"],
                profile_data=fast_profile_data,
                client=client
            )

        instant_reply = ai_service.get_instant_reply(request.message)
        if instant_reply:
            return {
                "reply": instant_reply,
                "messages_used": usage["messages_used"],
                "messages_remaining": usage["messages_remaining"]
            }
        
        async def extract_profile_later():
            try:
                await extractor_service.extract_and_save(
                    user_message=request.message,
                    user_id=user["id"],
                    client=client
                )
            except Exception as e:
                logger.warning(f"Profile extraction failed: {str(e)}")

        if not fast_profile_data:
            background_tasks.add_task(extract_profile_later)
        
        # Step 3: Get AI response from DeepSeek with profile personalization
        try:
            ai_reply = await ai_service.get_ai_response(
                user_message=request.message,
                user_id=user["id"],
                client=client,
                fresh_profile_data=fast_profile_data or None
            )
        except Exception as e:
            # If AI fails, we still consumed a message
            # Don't decrement - quota was already used
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI trainer temporarily unavailable: {str(e)}"
            )
        
        # Step 4: Return success response
        return {
            "reply": ai_reply,
            "messages_used": usage["messages_used"],
            "messages_remaining": usage["messages_remaining"]
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chat request: {str(e)}"
        )
