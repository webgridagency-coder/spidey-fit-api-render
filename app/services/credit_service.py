"""Plan-aware AI nutrition credit accounting for Ojas."""

from calendar import monthrange
from datetime import date
import logging
from typing import Any, Dict

from supabase import Client


logger = logging.getLogger(__name__)


class CreditService:
    """Manage the shared AI nutrition allowance used by photo and text scans."""

    PLAN_RULES = {
        "base": {"limit": 6, "period": "month"},
        "flow": {"limit": 6, "period": "day"},
        "orbit": {"limit": 6, "period": "day"},
    }
    DEFAULT_DAILY_CREDITS = 6

    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_plan(self, user_id: str) -> str:
        try:
            response = self.supabase.table("ojas_accounts").select("plan").eq("id", user_id).limit(1).execute()
            plan = str((response.data or [{}])[0].get("plan") or "base")
            return plan if plan in self.PLAN_RULES else "base"
        except Exception:
            logger.warning("Could not load nutrition plan for user %s", user_id[:8])
            return "base"

    @staticmethod
    def _period_bounds(period: str, today: date) -> tuple[str, str]:
        if period == "day":
            value = today.isoformat()
            return value, value
        return today.replace(day=1).isoformat(), today.replace(day=monthrange(today.year, today.month)[1]).isoformat()

    def _period_usage(self, user_id: str, period: str, today: date) -> int:
        start, end = self._period_bounds(period, today)
        response = self.supabase.table("user_food_credits").select("credits_used").eq(
            "user_id", user_id
        ).gte("date", start).lte("date", end).execute()
        return sum(int(row.get("credits_used", 0) or 0) for row in (response.data or []))

    async def get_or_create_daily_credits(self, user_id: str, today: date | None = None) -> Dict[str, Any]:
        today = today or date.today()
        today_str = today.isoformat()
        plan = self.get_plan(user_id)
        rule = self.PLAN_RULES[plan]
        try:
            response = self.supabase.table("user_food_credits").select("*").eq(
                "user_id", user_id
            ).eq("date", today_str).execute()
            if response.data:
                daily_used = int(response.data[0].get("credits_used", 0) or 0)
                if int(response.data[0].get("credits_limit", 0) or 0) != rule["limit"]:
                    self.supabase.table("user_food_credits").update({"credits_limit": rule["limit"]}).eq(
                        "user_id", user_id
                    ).eq("date", today_str).execute()
            else:
                created = self.supabase.table("user_food_credits").insert({
                    "user_id": user_id,
                    "date": today_str,
                    "credits_used": 0,
                    "credits_limit": rule["limit"],
                }).execute()
                if not created.data:
                    raise RuntimeError("Failed to create nutrition credit record")
                daily_used = 0

            used = daily_used if rule["period"] == "day" else self._period_usage(user_id, rule["period"], today)
            return {
                "credits_used": used,
                "credits_limit": rule["limit"],
                "remaining_credits": max(0, rule["limit"] - used),
                "date": today_str,
                "plan": plan,
                "period": rule["period"],
                "daily_credits_used": daily_used,
            }
        except Exception as exc:
            logger.error("Error loading nutrition credits for user %s: %s", user_id[:8], exc)
            return {
                "credits_used": rule["limit"],
                "credits_limit": rule["limit"],
                "remaining_credits": 0,
                "date": today_str,
                "plan": plan,
                "period": rule["period"],
                "daily_credits_used": 0,
            }

    async def check_remaining_credits(self, user_id: str) -> int:
        return int((await self.get_or_create_daily_credits(user_id))["remaining_credits"])

    async def consume_credit(self, user_id: str, amount: int = 1) -> Dict[str, Any]:
        if amount < 1:
            raise ValueError("Credit amount must be positive")
        today = date.today()
        current = await self.get_or_create_daily_credits(user_id, today)
        if current["remaining_credits"] < amount:
            raise ValueError("AI nutrition allowance reached")
        new_daily_used = int(current["daily_credits_used"]) + amount
        response = self.supabase.table("user_food_credits").update({
            "credits_used": new_daily_used,
            "credits_limit": current["credits_limit"],
        }).eq("user_id", user_id).eq("date", today.isoformat()).execute()
        if not response.data:
            raise RuntimeError("Failed to update nutrition credit usage")
        new_used = int(current["credits_used"]) + amount
        return {
            **current,
            "credits_used": new_used,
            "daily_credits_used": new_daily_used,
            "remaining_credits": max(0, int(current["credits_limit"]) - new_used),
        }

    async def has_credits(self, user_id: str) -> bool:
        return await self.check_remaining_credits(user_id) > 0

    async def limit_message(self, user_id: str) -> str:
        info = await self.get_or_create_daily_credits(user_id)
        if info["plan"] in {"flow", "orbit"}:
            return f"You’ve used today’s 6 AI nutrition scans. Your {info['plan'].title()} allowance resets tomorrow."
        return "You’ve used your 6 free AI nutrition scans for this month. Upgrade to Ojas Flow for 6 scans every day."
