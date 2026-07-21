"""Server-authorized operations console for Ojas owners."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.database import get_supabase_service
from app.dependencies import get_current_admin
from app.schemas.admin import AdminPlanUpdate, AdminQuotaReset, AdminStatusUpdate
from app.services.admin_service import AdminService


router = APIRouter()


@router.get("/me")
async def admin_me(admin: dict = Depends(get_current_admin)):
    return {"id": admin.get("id"), "email": admin.get("email"), "role": admin.get("admin_role", "owner")}


@router.get("/overview")
async def overview(
    days: int = Query(7, ge=7, le=30),
    admin: dict = Depends(get_current_admin),
    client: Client = Depends(get_supabase_service),
):
    del admin
    return await asyncio.to_thread(AdminService(client).overview, days)


@router.get("/users")
async def users(
    query: str = Query("", max_length=120),
    plan: str = Query("all", pattern="^(all|base|flow|orbit)$"),
    status_filter: str = Query("all", alias="status", pattern="^(all|active|suspended)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=50),
    admin: dict = Depends(get_current_admin),
    client: Client = Depends(get_supabase_service),
):
    del admin
    return await asyncio.to_thread(AdminService(client).list_users, query, plan, status_filter, page, page_size)


@router.get("/users/{user_id}")
async def user_detail(
    user_id: str,
    admin: dict = Depends(get_current_admin),
    client: Client = Depends(get_supabase_service),
):
    del admin
    result = await asyncio.to_thread(AdminService(client).user_detail, user_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return result


@router.patch("/users/{user_id}/plan")
async def update_plan(
    user_id: str,
    payload: AdminPlanUpdate,
    admin: dict = Depends(get_current_admin),
    client: Client = Depends(get_supabase_service),
):
    result = await asyncio.to_thread(AdminService(client).update_plan, admin, user_id, payload.plan, payload.reason)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return result


@router.patch("/users/{user_id}/status")
async def update_status(
    user_id: str,
    payload: AdminStatusUpdate,
    admin: dict = Depends(get_current_admin),
    client: Client = Depends(get_supabase_service),
):
    if str(admin.get("id")) == user_id and not payload.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot suspend your own owner account.")
    result = await asyncio.to_thread(AdminService(client).update_status, admin, user_id, payload.is_active, payload.reason)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return result


@router.post("/users/{user_id}/quota/reset")
async def reset_quota(
    user_id: str,
    payload: AdminQuotaReset,
    admin: dict = Depends(get_current_admin),
    client: Client = Depends(get_supabase_service),
):
    return await asyncio.to_thread(AdminService(client).reset_quota, admin, user_id, payload.reason)


@router.get("/audit")
async def audit(
    limit: int = Query(30, ge=1, le=100),
    admin: dict = Depends(get_current_admin),
    client: Client = Depends(get_supabase_service),
):
    del admin
    return await asyncio.to_thread(AdminService(client).audit_log, limit)
