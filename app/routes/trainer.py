"""
Trainer API routes - message quota enforcement and AI chat
"""

import asyncio
import json
import logging
import time
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from supabase import Client

logger = logging.getLogger(__name__)

from app.database import get_supabase
from app.dependencies import get_current_user
from app.schemas.trainer import TrainerQuotaResponse, TrainerUseResponse, TrainerChatRequest, TrainerChatResponse, TrainerHistoryMessage
from app.services.trainer_service import TrainerService
from app.services.ai_trainer_service import AITrainerService
from app.services.profile_extractor_service import ProfileExtractorService


router = APIRouter()


@router.get("/history", response_model=list[TrainerHistoryMessage])
async def get_trainer_history(user: dict = Depends(get_current_user)):
    """Return the persistent Ojas thread for this member across devices."""
    from app.database import SupabaseClient
    client = SupabaseClient.get_service_client()
    try:
        rows = await asyncio.to_thread(
            lambda: client.table("trainer_messages").select("id,role,content,created_at").eq(
                "user_id", user["id"]
            ).order("created_at", desc=True).limit(40).execute().data or []
        )
        return list(reversed(rows))
    except Exception:
        logger.exception("Failed to load coach history for user=%s", user["id"][:8])
        return []


@router.delete("/history")
async def clear_trainer_history(user: dict = Depends(get_current_user)):
    """Clear only chat messages; fitness, meal and workout memory remains intact."""
    from app.database import SupabaseClient
    client = SupabaseClient.get_service_client()
    service = AITrainerService()
    await asyncio.to_thread(service.clear_conversation_history, user["id"], client)
    return {"success": True}


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
        
        if quota["messages_remaining"] is not None and quota["messages_remaining"] <= 0:
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

        saved_history = await asyncio.to_thread(ai_service.get_saved_conversation_history, user["id"], client)
        conversation_history = saved_history or [
            {"role": item.role, "content": item.content} for item in request.history
        ]
        await asyncio.to_thread(
            ai_service.save_conversation_message, user["id"], "user", request.message, client
        )

        # Step 3: Get Ojas response with persistent personalization
        try:
            ai_reply = await ai_service.get_ai_response(
                user_message=request.message,
                user_id=user["id"],
                client=client,
                fresh_profile_data=fast_profile_data or None,
                conversation_history=conversation_history,
            )
            await asyncio.to_thread(
                ai_service.save_conversation_message,
                user["id"], "assistant", ai_reply, client, None, ai_service.last_provider,
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
            "messages_remaining": usage["messages_remaining"],
            "plan": usage["plan"],
            "period": usage["period"],
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


@router.post("/chat/stream")
async def stream_chat_with_trainer(
    request: TrainerChatRequest,
    user: dict = Depends(get_current_user),
):
    """Stream coach tokens as server-sent events with request timing metadata."""
    from app.database import SupabaseClient

    client = SupabaseClient.get_service_client()
    trainer_service = TrainerService(client)
    try:
        # increment_usage already enforces the active plan. Calling get_quota
        # first repeated the same database work and delayed every first token.
        usage = await trainer_service.increment_usage(user["id"])
    except Exception as exc:
        if "limit exceeded" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Coaching allowance reached") from exc
        raise
    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    extractor = ProfileExtractorService()
    fresh_profile_data = extractor.extract_profile_data_fast(request.message)
    service = AITrainerService()
    client_history = [{"role": item.role, "content": item.content} for item in request.history]

    async def event_stream():
        first_token_at = None
        full_reply = []
        try:
            yield f"event: meta\ndata: {json.dumps({'request_id': request_id, **usage})}\n\n"
            # Push headers/meta through buffering proxies before provider tokens arrive.
            yield ":" + (" " * 2048) + "\n\n"
            history_task = asyncio.to_thread(service.get_saved_conversation_history, user["id"], client)
            save_user_task = asyncio.to_thread(
                service.save_conversation_message, user["id"], "user", request.message, client, request_id
            )
            profile_task = (
                extractor.save_profile_data(user_id=user["id"], profile_data=fresh_profile_data, client=client)
                if fresh_profile_data else asyncio.sleep(0)
            )
            saved_history, _, _ = await asyncio.gather(history_task, save_user_task, profile_task)
            conversation_history = saved_history or client_history
            async for token in service.stream_ai_response(
                user_message=request.message,
                user_id=user["id"],
                client=client,
                fresh_profile_data=fresh_profile_data or None,
                conversation_history=conversation_history,
            ):
                if first_token_at is None:
                    first_token_at = time.monotonic()
                full_reply.append(token)
                yield f"event: delta\ndata: {json.dumps({'text': token})}\n\n"
            elapsed_ms = round((time.monotonic() - started) * 1000)
            first_token_ms = round(((first_token_at or time.monotonic()) - started) * 1000)
            reply_text = "".join(full_reply).strip()
            if reply_text:
                await asyncio.to_thread(
                    service.save_conversation_message,
                    user["id"], "assistant", reply_text, client, request_id, service.last_provider,
                )
            logger.info("coach_stream_complete request_id=%s user=%s first_token_ms=%s total_ms=%s chars=%s", request_id, user["id"][:8], first_token_ms, elapsed_ms, len("".join(full_reply)))
            yield f"event: done\ndata: {json.dumps({'request_id': request_id, 'first_token_ms': first_token_ms, 'total_ms': elapsed_ms, 'provider': service.last_provider})}\n\n"
        except Exception:
            logger.exception("coach_stream_failed request_id=%s user=%s", request_id, user["id"][:8])
            yield f"event: error\ndata: {json.dumps({'request_id': request_id, 'message': 'Ojas could not finish this reply. Try again.'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Content-Encoding": "none", "Connection": "keep-alive", "X-Request-ID": request_id},
    )
