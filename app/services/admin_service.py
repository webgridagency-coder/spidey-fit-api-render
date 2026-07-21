"""Read-only operations telemetry and tightly scoped account controls for Ojas admins."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any

from supabase import Client

from app.config import settings


logger = logging.getLogger(__name__)


class AdminService:
    PLAN_LIMITS = {
        "base": "5 messages / day",
        "flow": "50 messages / month",
        "orbit": "Unlimited coaching",
    }

    def __init__(self, client: Client):
        self.client = client

    @staticmethod
    def _day(value: Any) -> str:
        return str(value or "")[:10]

    @staticmethod
    def _latest(*values: Any) -> str | None:
        clean = [str(value) for value in values if value]
        return max(clean) if clean else None

    def _select_since(self, table: str, columns: str, field: str, since: str) -> list[dict]:
        try:
            return self.client.table(table).select(columns).gte(field, since).execute().data or []
        except Exception as exc:
            logger.warning("Admin telemetry could not read %s: %s", table, type(exc).__name__)
            return []

    def _audit(self, actor: dict, action: str, target_user_id: str | None, details: dict) -> bool:
        event = {
            "actor_user_id": actor.get("id"),
            "actor_email": actor.get("email"),
            "action": action,
            "target_user_id": target_user_id,
            "details": details,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("admin_audit %s", event)
        try:
            self.client.table("admin_audit_logs").insert(event).execute()
            return True
        except Exception:
            # Audit migration is optional during rollout. Structured server
            # logging remains active, and the action itself never fails open.
            return False

    def overview(self, days: int = 7) -> dict:
        days = max(7, min(days, 30))
        today = date.today()
        start_day = today - timedelta(days=days - 1)
        start_iso = f"{start_day.isoformat()}T00:00:00+00:00"

        accounts = self.client.table("ojas_accounts").select(
            "id,email,is_active,plan,created_at,updated_at"
        ).order("created_at", desc=True).execute().data or []
        workouts = self._select_since("workouts", "user_id,date,muscle,completed_at,created_at", "date", start_day.isoformat())
        meals = self._select_since("food_entries", "user_id,date,source,created_at", "date", start_day.isoformat())
        messages = self._select_since("trainer_messages", "user_id,role,provider,request_id,created_at", "created_at", start_iso)
        forms = self._select_since("form_sessions", "user_id,form_score,confidence_level,created_at", "created_at", start_iso)
        usage = self._select_since("trainer_usage", "user_id,date,messages_used", "date", start_day.isoformat())

        active_ids = {
            str(row.get("user_id"))
            for rows in (workouts, meals, messages, forms)
            for row in rows
            if row.get("user_id")
        }
        active_accounts = [row for row in accounts if row.get("is_active", True)]
        new_accounts = [row for row in accounts if self._day(row.get("created_at")) >= start_day.isoformat()]
        today_text = today.isoformat()
        assistant_messages = [row for row in messages if row.get("role") == "assistant"]
        user_messages = [row for row in messages if row.get("role") == "user"]
        completed_workouts = [row for row in workouts if row.get("completed_at")]
        form_scores = [float(row.get("form_score")) for row in forms if row.get("form_score") is not None]

        daily = { (start_day + timedelta(days=index)).isoformat(): {
            "date": (start_day + timedelta(days=index)).isoformat(),
            "new_users": 0,
            "workouts": 0,
            "meals": 0,
            "coach_replies": 0,
        } for index in range(days) }
        for row in accounts:
            key = self._day(row.get("created_at"))
            if key in daily: daily[key]["new_users"] += 1
        for row in workouts:
            key = self._day(row.get("date"))
            if key in daily: daily[key]["workouts"] += 1
        for row in meals:
            key = self._day(row.get("date"))
            if key in daily: daily[key]["meals"] += 1
        for row in assistant_messages:
            key = self._day(row.get("created_at"))
            if key in daily: daily[key]["coach_replies"] += 1

        plans = Counter((row.get("plan") or "base") for row in accounts)
        providers = Counter((row.get("provider") or "unknown") for row in assistant_messages)
        meal_sources = Counter((row.get("source") or "unknown") for row in meals)
        today_usage = sum(int(row.get("messages_used", 0) or 0) for row in usage if self._day(row.get("date")) == today_text)

        recent_activity: list[dict] = []
        account_emails = {str(row.get("id")): row.get("email") for row in accounts}
        for row in accounts[:8]:
            recent_activity.append({"type": "signup", "user_id": row.get("id"), "label": "New member joined", "email": row.get("email"), "at": row.get("created_at")})
        for row in workouts[-8:]:
            recent_activity.append({"type": "workout", "user_id": row.get("user_id"), "label": f"{row.get('muscle') or 'Workout'} saved", "email": account_emails.get(str(row.get("user_id"))), "at": row.get("completed_at") or row.get("created_at") or row.get("date")})
        for row in assistant_messages[-8:]:
            recent_activity.append({"type": "coach", "user_id": row.get("user_id"), "label": "Ojas reply completed", "email": account_emails.get(str(row.get("user_id"))), "at": row.get("created_at")})
        recent_activity = sorted(recent_activity, key=lambda item: str(item.get("at") or ""), reverse=True)[:12]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_days": days,
            "metrics": {
                "total_users": len(accounts),
                "active_accounts": len(active_accounts),
                "active_users": len(active_ids),
                "new_users": len(new_accounts),
                "workouts_today": sum(1 for row in workouts if self._day(row.get("date")) == today_text),
                "meals_today": sum(1 for row in meals if self._day(row.get("date")) == today_text),
                "coach_messages_today": sum(1 for row in user_messages if self._day(row.get("created_at")) == today_text),
                "form_sessions": len(forms),
            },
            "plans": [{"plan": plan, "users": plans.get(plan, 0), "allowance": self.PLAN_LIMITS[plan]} for plan in ("base", "flow", "orbit")],
            "trend": list(daily.values()),
            "ai_health": {
                "status": "operational" if settings.GEMINI_API_KEY else "configuration_required",
                "requests": len(user_messages),
                "completed_replies": len(assistant_messages),
                "completion_rate": round((len(assistant_messages) / len(user_messages) * 100), 1) if user_messages else 100.0,
                "providers": dict(providers),
                "last_reply_at": max((str(row.get("created_at")) for row in assistant_messages), default=None),
                "messages_used_today": today_usage,
            },
            "quality": {
                "workout_completion_rate": round((len(completed_workouts) / len(workouts) * 100), 1) if workouts else 0,
                "average_form_score": round(sum(form_scores) / len(form_scores), 1) if form_scores else None,
                "meal_sources": dict(meal_sources),
            },
            "recent_activity": recent_activity,
        }

    def list_users(self, query: str = "", plan: str = "all", status_filter: str = "all", page: int = 1, page_size: int = 20) -> dict:
        rows = self.client.table("ojas_accounts").select(
            "id,email,is_active,plan,created_at,updated_at"
        ).order("created_at", desc=True).execute().data or []
        needle = query.strip().lower()
        if needle:
            rows = [row for row in rows if needle in str(row.get("email") or "").lower() or needle in str(row.get("id") or "").lower()]
        if plan in self.PLAN_LIMITS:
            rows = [row for row in rows if (row.get("plan") or "base") == plan]
        if status_filter == "active": rows = [row for row in rows if row.get("is_active", True)]
        if status_filter == "suspended": rows = [row for row in rows if not row.get("is_active", True)]

        total = len(rows)
        start = (max(page, 1) - 1) * page_size
        page_rows = rows[start:start + page_size]
        ids = [row["id"] for row in page_rows]
        profiles: dict[str, dict] = {}
        last_activity: dict[str, str] = {}
        usage_map: dict[str, int] = defaultdict(int)
        if ids:
            try:
                profile_rows = self.client.table("user_profile").select(
                    "user_id,goal,experience_level,onboarding_completed"
                ).in_("user_id", ids).execute().data or []
                profiles = {str(row.get("user_id")): row for row in profile_rows}
            except Exception: pass
            for table, columns, field in (
                ("workouts", "user_id,created_at,completed_at,date", "created_at"),
                ("food_entries", "user_id,created_at", "created_at"),
                ("trainer_messages", "user_id,created_at", "created_at"),
                ("form_sessions", "user_id,created_at", "created_at"),
            ):
                try:
                    activity_rows = self.client.table(table).select(columns).in_("user_id", ids).order(field, desc=True).execute().data or []
                    for item in activity_rows:
                        uid = str(item.get("user_id"))
                        candidate = self._latest(item.get("completed_at"), item.get("created_at"), item.get("date"))
                        if candidate and (uid not in last_activity or candidate > last_activity[uid]): last_activity[uid] = candidate
                except Exception: pass
            try:
                today_usage = self.client.table("trainer_usage").select("user_id,messages_used").in_("user_id", ids).eq("date", date.today().isoformat()).execute().data or []
                for item in today_usage: usage_map[str(item.get("user_id"))] += int(item.get("messages_used", 0) or 0)
            except Exception: pass

        users = []
        for row in page_rows:
            uid = str(row.get("id"))
            profile = profiles.get(uid, {})
            users.append({
                **row,
                "plan": row.get("plan") or "base",
                "goal": profile.get("goal"),
                "experience_level": profile.get("experience_level"),
                "onboarding_completed": bool(profile.get("onboarding_completed")),
                "last_activity_at": last_activity.get(uid),
                "messages_used_today": usage_map.get(uid, 0),
            })
        return {"users": users, "total": total, "page": max(page, 1), "page_size": page_size, "pages": max(1, (total + page_size - 1) // page_size)}

    def user_detail(self, user_id: str) -> dict | None:
        accounts = self.client.table("ojas_accounts").select("id,email,is_active,plan,created_at,updated_at").eq("id", user_id).limit(1).execute().data or []
        if not accounts: return None
        account = accounts[0]
        def query(table: str, columns: str, order_field: str, limit: int = 8) -> list[dict]:
            try: return self.client.table(table).select(columns).eq("user_id", user_id).order(order_field, desc=True).limit(limit).execute().data or []
            except Exception: return []
        profile_rows = query("user_profile", "user_id,goal,experience_level,activity_level,diet_preference,cuisine_preference,onboarding_completed,calories_target,protein_target,updated_at", "updated_at", 1)
        workouts = query("workouts", "id,date,muscle,completed_at,created_at", "date")
        meals = query("food_entries", "id,date,meal_type,calories,protein,source,created_at", "created_at")
        forms = query("form_sessions", "id,exercise_name,reps,sets,form_score,confidence_level,created_at", "created_at")
        usage = query("trainer_usage", "date,messages_used", "date", 14)
        messages = query("trainer_messages", "role,provider,created_at", "created_at", 30)
        return {"account": {**account, "plan": account.get("plan") or "base"}, "profile": profile_rows[0] if profile_rows else None, "workouts": workouts, "meals": meals, "form_sessions": forms, "usage": usage, "coach": {"messages": len([row for row in messages if row.get("role") == "user"]), "replies": len([row for row in messages if row.get("role") == "assistant"]), "last_provider": next((row.get("provider") for row in messages if row.get("provider")), None)}}

    def update_plan(self, actor: dict, user_id: str, plan: str, reason: str) -> dict | None:
        rows = self.client.table("ojas_accounts").update({"plan": plan, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", user_id).execute().data or []
        if not rows: return None
        audited = self._audit(actor, "user.plan_changed", user_id, {"plan": plan, "reason": reason})
        return {"user": rows[0], "audit_recorded": audited}

    def update_status(self, actor: dict, user_id: str, is_active: bool, reason: str) -> dict | None:
        rows = self.client.table("ojas_accounts").update({"is_active": is_active, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", user_id).execute().data or []
        if not rows: return None
        audited = self._audit(actor, "user.reactivated" if is_active else "user.suspended", user_id, {"reason": reason})
        return {"user": rows[0], "audit_recorded": audited}

    def reset_quota(self, actor: dict, user_id: str, reason: str) -> dict:
        today = date.today().isoformat()
        rows = self.client.table("trainer_usage").update({"messages_used": 0, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("user_id", user_id).eq("date", today).execute().data or []
        audited = self._audit(actor, "user.quota_reset", user_id, {"date": today, "reason": reason})
        return {"success": True, "updated_records": len(rows), "audit_recorded": audited}

    def audit_log(self, limit: int = 30) -> dict:
        try:
            rows = self.client.table("admin_audit_logs").select("id,actor_email,action,target_user_id,details,created_at").order("created_at", desc=True).limit(limit).execute().data or []
            return {"persistent": True, "events": rows}
        except Exception:
            return {"persistent": False, "events": [], "message": "Structured audit events are active in server logs. Apply the optional audit migration to retain them in the dashboard."}
