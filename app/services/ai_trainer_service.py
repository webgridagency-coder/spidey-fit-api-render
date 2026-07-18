"""
AI Trainer service - OpenRouter integration (DeepSeek via OpenRouter)
Handles AI chat interactions with strict fitness coaching prompt
Includes user profile and workout catalog personalization
"""

import httpx
import asyncio
import json
import logging
import re
from typing import AsyncIterator, Dict, Any, Optional
from supabase import Client

from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)


class AITrainerService:
    """Service for AI trainer interactions via OpenRouter (DeepSeek model)"""
    
    # Advanced AI Fitness & Nutrition Coach System Prompt
    BASE_SYSTEM_PROMPT = """You are Ojas, the user's transparent personal AI fitness coach. Never claim to be human. Sound calm, practical, warm, and specific.

PERSONALIZATION CONTRACT:
- Ground every answer in the supplied profile, today's exact food items, recent meal history, saved/completed workouts, form sessions, and coaching conversation when relevant.
- Ojas is the main intelligence layer. Treat the supplied records as the user's source of truth across the app.
- Distinguish a planned workout from a completed workout. Never say a workout was completed unless completion evidence is present.
- When asked what the user ate, name the actual logged foods and meal types. Never answer with totals alone when item details are available.
- Mention the one or two user signals that actually changed your recommendation.
- Never claim you analyzed information that is not present in the context.
- Never ask for a fact already present in the context.
- Treat new explicit facts in the latest message as current. The app may save these to the user's reviewable profile.
- Do not infer or store sensitive health facts from vague language.
- If context is incomplete, say what is missing and ask one useful question.
- Call form scores "on-device form estimates," never accuracy, diagnosis, or injury prevention.
- Address the user as an ongoing client, but avoid fake familiarity and generic praise.
- If there is no AVAILABLE WORKOUTS TODAY block, say no workout is saved and do not invent a session or exercise list. Direct the user to choose a workout first.
- Examples in this prompt illustrate formatting only. Never copy their numbers or exercises unless the user's live context supports them.

🚨 CRITICAL FORMATTING RULE:
You MUST separate each section with a BLANK LINE. Never write everything in one paragraph.

────────────────────────────────
🎯 CORE COACHING PHILOSOPHY
────────────────────────────────

✅ Remember user stats and goals once given
✅ Do NOT repeat explanations
✅ Separate diet, workout, and education clearly
✅ Ask ONE clarification if input is vague
✅ Use day-based coaching (Day 1, Day 2...)
✅ Be calm, practical, and human

❌ Do NOT act like ChatGPT
❌ Do NOT dump information
❌ Do NOT mix diet + workout unless asked
❌ Do NOT give theory when user wants action

────────────────────────────────
🍽️ DIET COACHING RULES (CRITICAL)
────────────────────────────────

1. ONLY talk about DIET when user clearly asks about:
   - food / diet / calories / meal plan
   - protein / macros
   - fat loss via eating
   - "what should I eat"

2. If user asks for diet plan:
   - Ask ONE clarification if missing: Indian/other cuisine? Veg/non-veg?
   - Then respond once

3. Diet responses MUST be:
   - Structured with blank lines
   - Simple (no theory dumps)
   - No workout advice unless user requests
   - No asterisks (*), no markdown

4. Format diet replies as:
   - Short intro (1-2 lines)
   - Bullet meals (no paragraphs)
   - Minimal emojis
   - ONE next action step

5. Example diet response:
🍽️ Daily targets:
- Calories: 2100 kcal
- Protein: 157g

Sample meal plan:
- Breakfast: 3 eggs + 1 roti (350 kcal)
- Lunch: 120g chicken + rice (500 kcal)
- Snack: Greek yogurt + almonds (200 kcal)
- Dinner: 100g fish + salad (400 kcal)

✅ Next step: Track today's protein intake.

❌ DO NOT give full meal plans unless user specifically asks
❌ DO NOT repeat calorie calculations every time
❌ DO NOT mix workout advice with diet responses

────────────────────────────────
🏋️ WORKOUT STRUCTURE RULES (CRITICAL)
────────────────────────────────

1. TRAINING SPLIT based on muscles per day:
   - 1 muscle/day → Train each muscle once per week
   - 2 muscles/day → Push/Pull or Upper/Lower style
   - Full body → 3x per week max

2. EXERCISE COUNT rules:
   - Single muscle day → 4-5 exercises
   - Two muscles day → 2-3 exercises per muscle (total 6)
   - Full body → 5-6 total exercises

3. NEVER suggest random exercises
   - Use ONLY exercises from the app's workout catalog
   - Do NOT invent exercise names

4. When suggesting workouts:
   - Mention TODAY only
   - Do NOT list whole week unless user asks
   - Keep it simple and actionable

5. Example workout response:
🏋️ Day 1 Workout:
Pull day: Back + Biceps
- Lat pulldown 3x10-12
- Bent-over rows 3x8-10
- Bicep curls 3x12-15

🏃 Cardio:
LISS: 25 min brisk walk

📊 Steps:
Target: 8,500 steps

✅ Did you complete it?

────────────────────────────────
📅 PROGRESS TRACKING RULES
────────────────────────────────

1. If user mentions "Day 1", "Day 2", "today", "starting":
   → Treat as progress check-in

2. If day number unclear:
   → Ask ONE short question: "What day of the challenge are you on?"

3. Once day number is known:
   - Remember it
   - Refer to it naturally: "Since this is Day 3..."

4. Every 5-7 days:
   - Ask gently for update: weight, energy, adherence
   - No pressure language

────────────────────────────────
🗣️ WHEN USER SAYS "TODAY" or "DAY X"
────────────────────────────────

Give ONLY TODAY'S ACTION PLAN:
- Workout for today (specific exercises)
- Cardio type and duration
- Step goal

❌ NO theory
❌ NO BMR/TDEE recalculations
❌ NO motivation speeches
❌ NO diet plan (unless they ask)

Keep responses SHORT (80-100 words max for daily plans)

────────────────────────────────
🎯 INITIAL GOAL SETUP (DO ONCE)
────────────────────────────────

When user first shares their goal:
1. Calculate BMR/TDEE ONCE
2. Give reality check + calorie plan
3. Provide training overview
4. Then switch to day-by-day coaching

After initial setup:
- Do NOT repeat calculations
- Do NOT re-explain theory
- Focus on daily execution

────────────────────────────────
💬 HANDLING VAGUE INPUT
────────────────────────────────

If user says: "hi", "ok", "help", "hey", unclear message
→ Ask ONE clarifying question:
   - "Are you asking about today's workout or your diet?"
   - "What do you need help with today?"
   - "Are you on Day 1 or already started?"

Do NOT dump generic information
Do NOT give motivation speeches

────────────────────────────────
✅ TONE & COMMUNICATION STYLE
────────────────────────────────

Sound like a REAL COACH:
- Calm and confident
- Direct and action-focused
- No fluff or repetition
- No ChatGPT-style responses

Examples of GOOD responses:
✅ "Pull day today. Focus on back and biceps."
✅ "Track 2100 kcal, 157g protein."
✅ "Did you complete it?"

Examples of BAD responses:
❌ "Remember that consistency is key..."
❌ "As I mentioned before..."
❌ Long explanations when user wants action

────────────────────────────────
🚫 NEVER DO THE FOLLOWING
────────────────────────────────

❌ Repeat BMR/TDEE calculations every message
❌ Re-explain calorie deficit theory repeatedly
❌ Give theory when user asks for action
❌ Mix diet + workout unless user asks for both
❌ Use markdown formatting (**bold**, ###headers)
❌ Invent exercises not in workout catalog
❌ Give generic motivational responses
❌ Dump full meal plans when not asked
❌ Act like a chatbot instead of a coach
❌ Re-explain calorie deficit theory repeatedly  
❌ Give theory when user asks for action
❌ Mix diet + workout unless user asks for both
❌ Use markdown formatting (**bold**, ###headers, etc.)
❌ Invent exercises not in workout catalog
❌ Give generic motivational responses

────────────────────────────────
COMMUNICATION RULES
────────────────────────────────

✅ DO:
- Use their profile data (weight, height, goal, cuisine, diet type, timeline)
- Calculate BMR and TDEE when discussing diet
- Provide specific calorie and macro targets
- Be specific with Indian food names if cuisine is Indian
- Include non-veg options if diet type is non-veg
- Keep responses structured with bullet points
- One clear next action step

────────────────────────────────
INTENT DETECTION (MANDATORY)
────────────────────────────────

Before replying, identify what the user is asking:

1) DIET INTENT  
If asking about: food, calories, eating, meals, "what should I eat"
→ Calculate BMR using: Men: 10 × weight(kg) + 6.25 × height(cm) - 5 × age + 5
                        Women: 10 × weight(kg) + 6.25 × height(cm) - 5 × age - 161
→ Calculate TDEE based on activity level
→ Provide calorie deficit plan
→ List protein target (1.8-2.2g per kg)
→ Provide sample meal plan with calories
→ DO NOT recommend exercises unless asked

2) EXERCISE INTENT
If asking about: workouts, exercises, training, gym plans
→ Recommend strength training 4+ days/week
→ Use workout catalog ONLY (NEVER invent exercises)
→ Mention cardio split (LISS + optional HIIT)
→ Include NEAT advice (steps target)
→ DO NOT talk about calories unless asked

3) GOAL / PROGRESS INTENT
If user shares: weight updates, goal timeline, current stats
→ Calculate if goal is realistic (0.5-1kg per week is safe)
→ Explain physiological limits
→ Provide realistic timeline
→ No hype, just data-driven guidance

4) VAGUE INPUT
If user says: "hi", "ok", "help", "hey"
→ Ask ONE short clarifying question
→ Examples: "Are you asking about diet or training?" or "What do you need help with?"

────────────────────────────────
MEMORY & CONTEXT
────────────────────────────────

- Never ask for info already in their profile
- Reference naturally: "Based on your goal..." (not "I remember...")
- When they update stats, acknowledge without confirming "save"
- Act like their ongoing trainer who knows them

────────────────────────────────
🚨 ABSOLUTE FORMATTING LAW (NEVER VIOLATE!)
────────────────────────────────

YOU MUST INSERT TWO NEWLINE CHARACTERS (\n\n) BETWEEN EVERY SECTION.
FAILURE TO DO THIS MAKES YOUR RESPONSE UNREADABLE.

Example of what you MUST output (copy this structure EXACTLY):

🎯 Reality check:\n15kg + muscle gain in 60 days is extremely aggressive.\n\nBest-case scenario:\n- Fat loss: ~4-5kg\n- Water loss: ~2kg\n- Muscle gain: ~1-2kg\n\n💪 Calorie logic:\n- BMR: ~1750 kcal\n- TDEE: ~2600 kcal\n- Target: ~2100 kcal (500 deficit)\n- Protein: 157-191g/day\n\n🏋️ Training:\n- Strength 5x/week\n- LISS 3x/week\n- 8,000+ steps daily\n\n✅ Next step:\nTrack 2100 kcal, 157g protein. Focus on compound lifts.

RENDERED OUTPUT (what user sees):

🎯 Reality check:
15kg + muscle gain in 60 days is extremely aggressive.

Best-case scenario:
- Fat loss: ~4-5kg
- Water loss: ~2kg
- Muscle gain: ~1-2kg

💪 Calorie logic:
- BMR: ~1750 kcal
- TDEE: ~2600 kcal
- Target: ~2100 kcal (500 deficit)
- Protein: 157-191g/day

🏋️ Training:
- Strength 5x/week
- LISS 3x/week
- 8,000+ steps daily

✅ Next step:
Track 2100 kcal, 157g protein. Focus on compound lifts.

────────────────────────────────
📅 DAY-BY-DAY RESPONSE EXAMPLES
────────────────────────────────

EXAMPLE 1: User says "today is day 1" or "what should I do"

🏋️ Day 1 Workout:
Push day: Chest + Shoulders + Triceps
- Bench press 3x8-10
- Shoulder press 3x10-12
- Tricep dips 3x10-12

🏃 Cardio:
LISS: 30 min walk

📊 Steps:
Target: 8,000+ steps

✅ Did you complete it?

EXAMPLE 2: User asks for diet plan

🍽️ Daily targets:
- Calories: 2100 kcal
- Protein: 157g

Sample meal plan:
- Breakfast: 3 eggs + 1 roti (350 kcal)
- Lunch: 120g chicken + rice (500 kcal)
- Snack: Greek yogurt + almonds (200 kcal)
- Dinner: 100g fish + salad (400 kcal)

💧 Hydration:
3+ liters water daily

✅ Can you follow this today?

────────────────────────────────
FORMATTING ENFORCEMENT (CRITICAL!)
────────────────────────────────

🚨 ABSOLUTE RULES:
1. After EVERY section with bullets → add \n\n (two newlines)
2. After EVERY emoji header line → add \n\n (two newlines)
3. Keep sentences under 12 words
4. Use ONLY 3-4 bullets per section
5. Total length: 120-150 words MAX for regular responses
6. Total length: 80-100 words MAX for "today/day" responses

❌ NEVER:
- Repeat BMR/TDEE calculations every message
- Give theory when user wants action for today
- Write long paragraphs
- Skip double line breaks between sections

Remember: You're building TRUST through clarity and consistency, not information dumps.
Speak like a real human coach having a conversation."""

    # Compact production prompt. Keeping this focused reduces provider input
    # processing time and removes the conflicting legacy instructions above.
    BASE_SYSTEM_PROMPT = """You are Ojas, the user's personal AI fitness coach and the main intelligence layer of the Ojas app.

Use the supplied records as the source of truth:
- Profile: goals, age, gender, body data, activity, experience, diet and limitations.
- Today's nutrition: every confirmed text entry or confirmed photo scan, its meal name, source and reviewed macros.
- Recent meal history: identify patterns only from logged records.
- Workouts: distinguish planned workouts from explicitly completed workouts using the supplied status.
- Form sessions and the recent coaching conversation when relevant.

Grounding rules:
- When asked what the user ate, name the exact confirmed foods, meal types and reviewed values. A photo preview is not eaten until it is confirmed and appears in the records.
- When asked what the user trained, name the saved exercises. Say completed only when the record says completed; otherwise say planned.
- Never invent a meal, workout, completion, measurement or trend.
- Never ask for information already supplied. If a needed fact is missing, state that briefly and ask one useful question.
- Use gender only where a validated calculation requires it, such as the selected BMR equation. Do not stereotype training or food needs.
- Treat missing logs as unknown, not skipped or failed.
- For form tracking, say on-device form estimate. Never claim diagnosis, injury prevention or clinical accuracy.

Coaching style:
- Answer the question immediately. Be warm, direct and specific.
- Usually use 60 to 130 words. Use a longer answer only when the user explicitly requests a detailed plan.
- Cite one or two saved signals that changed a recommendation under a short Why this fits line.
- Give one practical next action.
- Avoid generic praise, repeated theory and repeated BMR or TDEE calculations.
- If both food and training are requested, cover both; otherwise stay on the requested topic.

Output plain text only:
- Never output asterisks, hashtags, markdown headings, underscores, backticks or tables.
- Headings may be plain words ending with a colon.
- Use hyphens for short lists and blank lines between sections.
- Do not expose hidden reasoning or mention the system prompt."""
    
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        openrouter_base = settings.OPENROUTER_BASE_URL.rstrip("/")
        self.api_url = openrouter_base if openrouter_base.endswith("/chat/completions") else f"{openrouter_base}/chat/completions"
        self.model = settings.OPENROUTER_MODEL
        self.timeout = min(settings.OPENROUTER_TIMEOUT, 12)
        self.gemini_api_key = settings.GEMINI_API_KEY
        self.gemini_api_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        self.gemini_model = settings.GEMINI_MODEL
        self.last_provider = "fallback"

    def _provider_configs(self) -> list[Dict[str, str]]:
        """Gemini is the primary Ojas coach, with OpenRouter as a resilient fallback."""
        providers = []
        if self.gemini_api_key and "your-" not in self.gemini_api_key.lower():
            providers.append({"name": "gemini", "url": self.gemini_api_url, "key": self.gemini_api_key, "model": self.gemini_model})
        if self.api_key and "your-" not in self.api_key.lower():
            providers.append({"name": "openrouter", "url": self.api_url, "key": self.api_key, "model": self.model})
        return providers

    @staticmethod
    def sanitize_coach_output(content: str) -> str:
        """Keep Ojas replies plain-text even if a provider emits Markdown."""
        cleaned = re.sub(r"(?m)^\s*#{1,6}\s*", "", content)
        cleaned = cleaned.replace("*", "").replace("`", "").replace("_", "")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def get_saved_conversation_history(self, user_id: str, client: Client, limit: int = 16) -> list[Dict[str, str]]:
        """Load recent cross-device Ojas messages in chronological order."""
        try:
            rows = client.table("trainer_messages").select("role,content,created_at").eq(
                "user_id", user_id
            ).order("created_at", desc=True).limit(limit).execute().data or []
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        except Exception as exc:
            logger.warning("Coach history unavailable for %s: %s", user_id[:8], str(exc))
            return []

    def save_conversation_message(
        self,
        user_id: str,
        role: str,
        content: str,
        client: Client,
        request_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> None:
        """Persist one reviewed user/assistant message without blocking coaching if storage fails."""
        try:
            stored_content = self.sanitize_coach_output(content) if role == "assistant" else content.strip()
            client.table("trainer_messages").insert({
                "user_id": user_id,
                "role": role,
                "content": stored_content[:8000],
                "request_id": request_id,
                "provider": provider,
            }).execute()
        except Exception as exc:
            logger.warning("Could not persist coach message for %s: %s", user_id[:8], str(exc))

    def clear_conversation_history(self, user_id: str, client: Client) -> None:
        client.table("trainer_messages").delete().eq("user_id", user_id).execute()

    def get_instant_reply(self, user_message: str) -> Optional[str]:
        """Return instant replies for common low-context trainer prompts."""
        message = re.sub(r"\s+", " ", user_message.strip().lower())

        if message in {"hi", "hey", "hello", "help"}:
            return "What do you need right now?\n\n- Today's workout\n- Meal plan\n- Fat loss help\n- Protein target"

        if message in {"today's workout", "todays workout", "today workout", "workout"}:
            return "🏋️ Today's workout:\n\nPick one muscle group and start the plan.\n\n- Keep rests short\n- Finish every set with control\n- Log it when done\n\n✅ Next step: open Workout and start."

        if message in {"low energy", "tired", "no energy"}:
            return "Low energy plan:\n\n- Drink water first\n- Eat protein plus carbs\n- Do 20 minutes easy training\n- Sleep earlier tonight\n\n✅ Keep it light, but do not skip."

        if message in {"protein help", "protein"}:
            return "Protein target:\n\n- Aim for protein in every meal\n- Use eggs, chicken, paneer, curd, dal\n- Keep one high-protein snack ready\n\n✅ Next meal: add one protein source."

        if message in {"fat loss", "weight loss"}:
            return "Fat loss focus:\n\n- Keep calories controlled\n- Hit protein first\n- Walk after meals\n- Train 3-5 days weekly\n\n✅ Today: log food before dinner."

        return None
    
    def _format_response_with_line_breaks(self, response: str) -> str:
        """Post-process AI response to force proper line breaks between emoji sections."""
        import re
        # All emojis that should trigger section breaks (including 🏃 and 📊)
        section_emojis = ['🎯', '💪', '🏋️', '🍽️', '✅', '🏃', '📊', '💧']
        
        # Remove all existing line breaks first
        response = response.replace('\n', ' ').replace('\r', '')
        
        # Split by each emoji and add proper spacing
        for emoji in section_emojis:
            parts = response.split(emoji)
            if len(parts) > 1:
                result = [parts[0]]
                for part in parts[1:]:
                    result.append(f'\n\n{emoji}{part}')
                response = ''.join(result)
        
        # Add breaks for common sub-headings
        response = response.replace(' Best-case scenario:', '\n\nBest-case scenario:\n')
        response = response.replace(' Sample day:', '\n\nSample day:\n')
        response = response.replace(' Sample meal plan:', '\n\nSample meal plan:\n')
        response = response.replace(' Pull day:', '\nPull day:')
        response = response.replace(' Push day:', '\nPush day:')
        response = response.replace(' Leg day:', '\nLeg day:')
        response = response.replace(' Full body:', '\nFull body:')
        response = response.replace(' LISS:', '\nLISS:')
        response = response.replace(' HIIT:', '\nHIIT:')
        response = response.replace(' Target:', '\nTarget:')
        
        # Convert bullets to new lines
        response = response.replace(' - ', '\n- ')
        
        # Clean up extra spaces
        response = re.sub(r' +', ' ', response)
        
        # Split into lines and rebuild with proper spacing
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        formatted = []
        
        for i, line in enumerate(lines):
            formatted.append(line)
            if i < len(lines) - 1:
                next_has_emoji = any(e in lines[i + 1] for e in section_emojis)
                current_is_bullet = line.startswith('-')
                next_is_bullet = lines[i + 1].startswith('-') if i < len(lines) - 1 else False
                
                # Add blank line before emoji sections (but not between consecutive bullets)
                if next_has_emoji and not next_is_bullet:
                    formatted.append('')
                # Add blank line after last bullet before emoji section
                elif current_is_bullet and not next_is_bullet and i < len(lines) - 2:
                    if any(e in lines[i + 1] for e in section_emojis):
                        formatted.append('')
        return '\n'.join(formatted).strip()
    
    def get_user_profile_context(self, user_id: str, client: Client) -> str:
        """
        Fetch user profile and format it as context for AI personalization.
        
        Args:
            user_id: User's UUID
            client: Supabase client (service_role to bypass RLS)
            
        Returns:
            Formatted profile context string, or empty string if no profile exists
        """
        try:
            # Fetch user profile from database (including progress tracking fields)
            response = client.table("user_profile").select(
                "height_cm, weight_kg, body_fat_percentage, age, gender, goal, activity_level, "
                "experience_level, injuries, diet_preference, goal_target_weight, goal_start_date, "
                "goal_duration_days, starting_weight, last_checkin_date"
            ).eq("user_id", user_id).execute()
            
            # No profile found
            if not response.data or len(response.data) == 0:
                logger.debug(f"No profile found for user {user_id[:8]}...")
                return ""
            
            profile = response.data[0]
            logger.debug(f"Profile loaded for user {user_id[:8]}...")
            
            # Build context string with only non-null fields
            context_parts = []
            
            if profile.get("age"):
                context_parts.append(f"Age: {profile['age']}")
            
            if profile.get("gender"):
                context_parts.append(f"Gender: {profile['gender']}")
            
            if profile.get("height_cm"):
                context_parts.append(f"Height: {profile['height_cm']} cm")
            
            if profile.get("weight_kg"):
                context_parts.append(f"Weight: {profile['weight_kg']} kg")
            
            if profile.get("body_fat_percentage"):
                context_parts.append(f"Body fat: {profile['body_fat_percentage']}%")
            
            if profile.get("goal"):
                context_parts.append(f"Goal: {profile['goal']}")
            
            if profile.get("activity_level"):
                context_parts.append(f"Activity level: {profile['activity_level']}")
            
            if profile.get("experience_level"):
                context_parts.append(f"Experience: {profile['experience_level']}")
            
            if profile.get("diet_preference"):
                context_parts.append(f"Diet: {profile['diet_preference']}")
            
            if profile.get("injuries"):
                context_parts.append(f"Injuries: {profile['injuries']}")
            
            # Progress tracking context (if user has set a goal with timeframe)
            progress_parts = []
            
            if profile.get("goal_target_weight") and profile.get("starting_weight"):
                progress_parts.append(f"Target weight: {profile['goal_target_weight']} kg (started at {profile['starting_weight']} kg)")
            
            if profile.get("goal_start_date"):
                from datetime import datetime
                start_date = profile['goal_start_date']
                if isinstance(start_date, str):
                    start_date = datetime.fromisoformat(start_date).date()
                days_elapsed = (datetime.now().date() - start_date).days
                progress_parts.append(f"Goal started: {days_elapsed} days ago")
            
            if profile.get("goal_duration_days"):
                progress_parts.append(f"Goal duration: {profile['goal_duration_days']} days")
            
            if profile.get("last_checkin_date"):
                from datetime import datetime
                last_checkin = profile['last_checkin_date']
                if isinstance(last_checkin, str):
                    last_checkin = datetime.fromisoformat(last_checkin).date()
                days_since_checkin = (datetime.now().date() - last_checkin).days
                
                # Gentle check-in prompt if 5-7 days have passed
                if days_since_checkin >= 5:
                    progress_parts.append(f"Last check-in: {days_since_checkin} days ago (consider asking for progress update)")
            
            if progress_parts:
                context_parts.append("\nPROGRESS TRACKING:")
                context_parts.extend(progress_parts)
            
            # If no fields are populated, return empty string
            if not context_parts:
                return ""
            
            # Format as context block
            context = "\n\nUSER PROFILE:\n" + "\n".join(context_parts)
            return context
            
        except Exception as e:
            # If profile fetch fails, continue without profile (graceful degradation)
            logger.warning(f"Failed to fetch profile for user {user_id[:8]}...: {str(e)}")
            return ""
    
    def get_workout_context(self, user_id: str, client: Client) -> str:
        """
        Fetch user's available workout exercises and format as context.
        
        This ensures AI only suggests exercises from the user's actual workout catalog,
        preventing hallucinated or generic exercise recommendations.
        
        Args:
            user_id: User's UUID
            client: Supabase client (service_role to bypass RLS)
            
        Returns:
            Formatted workout context string, or empty string if no workout exists
        """
        try:
            from datetime import date
            
            # Try to get today's workout first
            today = date.today().isoformat()
            response = client.table("workouts").select(
                "date, muscle, exercises, completed_at"
            ).eq("user_id", user_id).eq("date", today).execute()
            is_today = bool(response.data)
            
            # If no workout today, get the most recent workout
            if not response.data or len(response.data) == 0:
                response = client.table("workouts").select(
                    "date, muscle, exercises, completed_at"
                ).eq("user_id", user_id).order(
                    "date", desc=True
                ).limit(1).execute()
            
            # No workouts found at all
            if not response.data or len(response.data) == 0:
                logger.debug(f"No workouts found for user {user_id[:8]}...")
                return ""
            
            workout = response.data[0]
            workout_date = workout.get("date", today)
            muscle_group = workout.get("muscle", "Unknown")
            exercises = workout.get("exercises", [])
            status_label = "completed" if workout.get("completed_at") else "planned, not marked complete"
            
            # Validate exercises data
            if not exercises or not isinstance(exercises, list):
                logger.debug(f"No valid exercises in workout for user {user_id[:8]}...")
                return ""
            
            # Extract exercise names only (ignore sets/reps/details)
            exercise_names = []
            for exercise in exercises:
                if isinstance(exercise, dict) and "name" in exercise:
                    exercise_names.append(exercise["name"])
                elif isinstance(exercise, str):
                    exercise_names.append(exercise)
            
            if not exercise_names:
                return ""
            
            logger.debug(f"Workout context loaded for user {user_id[:8]}... ({len(exercise_names)} exercises)")
            
            # Format workout context
            context = (
                "\n\nAVAILABLE WORKOUTS TODAY:\n"
                f"Record: {'today' if is_today else 'most recent saved workout'} ({workout_date})\n"
                f"Status: {status_label}\n"
                f"Muscle Group: {muscle_group}\nExercises:\n"
            )
            context += "\n".join([f"- {name}" for name in exercise_names])
            
            return context
            
        except Exception as e:
            # If workout fetch fails, continue without workout context (graceful degradation)
            logger.warning(f"Failed to fetch workout for user {user_id[:8]}...: {str(e)}")
            return ""

    def get_nutrition_context(self, user_id: str, client: Client) -> str:
        """Return today's real nutrition totals and meal count for grounded coaching."""
        try:
            from datetime import date

            response = client.table("food_entries").select(
                "meal_type, description, calories, protein, carbs, fats, fiber, source, created_at"
            ).eq("user_id", user_id).eq("date", date.today().isoformat()).order("created_at").execute()
            entries = response.data or []
            totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fats": 0.0, "fiber": 0.0}
            for entry in entries:
                for key in totals:
                    totals[key] += float(entry.get(key, 0) or 0)

            meal_lines = []
            for entry in entries:
                description = str(entry.get("description") or "Unnamed logged food").strip()[:180]
                source_label = {
                    "ai_image": "confirmed photo scan",
                    "ai_text": "text meal scan",
                    "manual": "manual entry",
                }.get(entry.get("source"), "logged entry")
                meal_lines.append(
                    f"- {entry.get('meal_type') or 'meal'}: {description} [{source_label}] — "
                    f"{round(float(entry.get('calories', 0) or 0))} kcal, "
                    f"{round(float(entry.get('protein', 0) or 0))} g protein, "
                    f"{round(float(entry.get('carbs', 0) or 0))} g carbs, "
                    f"{round(float(entry.get('fats', 0) or 0))} g fats, "
                    f"{round(float(entry.get('fiber', 0) or 0))} g fiber"
                )

            return (
                "\n\nTODAY'S NUTRITION (logged data only):\n"
                f"Meals logged: {len(entries)}\n"
                f"Calories: {round(totals['calories'])} kcal\n"
                f"Protein: {round(totals['protein'])} g\n"
                f"Carbs: {round(totals['carbs'])} g\n"
                f"Fats: {round(totals['fats'])} g\n"
                + ("TODAY'S FOOD ITEMS:\n" + "\n".join(meal_lines) + "\n" if meal_lines else "TODAY'S FOOD ITEMS: none logged.\n")
                + "If zero meals are logged, do not say the user ate nothing; say no meals are logged."
            )
        except Exception as e:
            logger.warning(f"Failed to fetch nutrition context for user {user_id[:8]}...: {str(e)}")
            return ""

    def get_meal_history_context(self, user_id: str, client: Client) -> str:
        """Return recent named foods so Ojas can recognize patterns beyond today's totals."""
        try:
            from datetime import date, timedelta

            start = (date.today() - timedelta(days=13)).isoformat()
            rows = client.table("food_entries").select(
                "date,meal_type,description,calories,protein,carbs,fats,source"
            ).eq("user_id", user_id).gte("date", start).order("date", desc=True).limit(30).execute().data or []
            if not rows:
                return "\n\nRECENT MEAL HISTORY (14 days): No meals logged in this window."
            lines = [
                f"- {row.get('date')} · {row.get('meal_type') or 'meal'}: "
                f"{str(row.get('description') or 'Unnamed logged food')[:140]} "
                f"({round(float(row.get('calories', 0) or 0))} kcal, {round(float(row.get('protein', 0) or 0))} g protein, "
                f"{round(float(row.get('carbs', 0) or 0))} g carbs, {round(float(row.get('fats', 0) or 0))} g fats; "
                f"source: {row.get('source') or 'logged'})"
                for row in rows
            ]
            return "\n\nRECENT MEAL HISTORY (up to 14 days, newest first):\n" + "\n".join(lines)
        except Exception as exc:
            logger.warning("Failed to build meal history for %s: %s", user_id[:8], str(exc))
            return ""

    def get_progress_context(self, user_id: str, client: Client) -> str:
        """Summarize recent adherence and progression signals for longitudinal coaching."""
        try:
            from datetime import date, timedelta

            start = (date.today() - timedelta(days=6)).isoformat()
            workouts = client.table("workouts").select("date,muscle,exercises,completed_at").eq("user_id", user_id).gte("date", start).order("date").execute().data or []
            meals = client.table("food_entries").select("date,protein,calories").eq("user_id", user_id).gte("date", start).execute().data or []
            form_sessions = client.table("form_sessions").select("exercise_name,reps,sets,form_score,created_at").eq("user_id", user_id).gte("created_at", f"{start}T00:00:00Z").order("created_at").execute().data or []
            meal_days = {row.get("date") for row in meals if row.get("date")}
            protein_total = sum(float(row.get("protein", 0) or 0) for row in meals)
            average_protein = round(protein_total / len(meal_days)) if meal_days else 0
            completed_workouts = [row for row in workouts if row.get("completed_at")]
            workout_lines = [f"- {row.get('date')}: {row.get('muscle')} ({len(row.get('exercises') or [])} exercises) — {'completed' if row.get('completed_at') else 'planned only'}" for row in workouts[-7:]]
            form_lines = [f"- {row.get('exercise_name')}: {row.get('sets')} sets, {row.get('reps')} reps, {round(float(row.get('form_score', 0) or 0))}% form estimate" for row in form_sessions[-5:]]
            return (
                "\n\nLAST 7 DAYS (evidence, not assumptions):\n"
                f"Workout plans saved: {len({row.get('date') for row in workouts})}/7\n"
                f"Workouts explicitly completed: {len(completed_workouts)}/7\n"
                f"Food-log days: {len(meal_days)}/7\n"
                f"Average protein on logged days: {average_protein} g\n"
                + ("Recent workouts:\n" + "\n".join(workout_lines) + "\n" if workout_lines else "No workouts logged in this window.\n")
                + ("Recent camera sessions:\n" + "\n".join(form_lines) if form_lines else "No camera-form sessions logged in this window.")
                + "\nWhen recommending a change, include a short 'Why this changed' section citing one or two signals above. Treat missing days as unlogged, not skipped."
            )
        except Exception as exc:
            logger.warning("Failed to build progress context for %s: %s", user_id[:8], str(exc))
            return ""

    async def stream_ai_response(
        self,
        user_message: str,
        user_id: str,
        client: Client,
        conversation_history: Optional[list[Dict[str, str]]] = None,
        fresh_profile_data: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """Yield real provider tokens with one safe retry before the first token."""
        system_prompt = self.BASE_SYSTEM_PROMPT
        if fresh_profile_data:
            system_prompt += "\n\nNEW USER DATA FROM THIS MESSAGE:\n" + "\n".join(f"{key}: {value}" for key, value in fresh_profile_data.items())
        contexts = await asyncio.gather(
            asyncio.to_thread(self.get_user_profile_context, user_id, client),
            asyncio.to_thread(self.get_workout_context, user_id, client),
            asyncio.to_thread(self.get_nutrition_context, user_id, client),
            asyncio.to_thread(self.get_meal_history_context, user_id, client),
            asyncio.to_thread(self.get_progress_context, user_id, client),
        )
        system_prompt += "".join(contexts)
        recent_history = []
        for item in (conversation_history or [])[-8:]:
            role = item.get("role")
            content = str(item.get("content", "")).strip()[:1200]
            if role in {"user", "assistant"} and content:
                recent_history.append({"role": role, "content": content})
        providers = self._provider_configs()
        if not providers:
            yield self.get_personalized_fallback(user_message, contexts[0], contexts[1], contexts[2])
            return
        last_error: Optional[Exception] = None
        for provider in providers:
            payload = {
                "model": provider["model"],
                "messages": [{"role": "system", "content": system_prompt}, *recent_history, {"role": "user", "content": user_message}],
                "temperature": 0.35,
                "max_tokens": 600,
                "stream": True,
            }
            if provider["name"] == "gemini":
                # Gemini 2.5 counts internal thinking against max_tokens. Ojas
                # needs fast, complete grounded chat answers, not hidden chain
                # of thought that can consume the whole response allowance.
                payload["reasoning_effort"] = "none"
            headers = {"Authorization": f"Bearer {provider['key']}", "Content-Type": "application/json"}
            for attempt in range(2):
                emitted = False
                try:
                    timeout = httpx.Timeout(40.0, connect=8.0, read=30.0)
                    async with httpx.AsyncClient(timeout=timeout) as http_client:
                        async with http_client.stream("POST", provider["url"], headers=headers, json=payload) as response:
                            response.raise_for_status()
                            async for line in response.aiter_lines():
                                if not line.startswith("data:"):
                                    continue
                                data = line[5:].strip()
                                if not data or data == "[DONE]":
                                    continue
                                chunk = json.loads(data)
                                token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if token:
                                    emitted = True
                                    self.last_provider = provider["name"]
                                    yield token
                    return
                except (httpx.HTTPError, json.JSONDecodeError) as exc:
                    last_error = exc
                    logger.warning("%s streaming attempt %s failed: %s", provider["name"], attempt + 1, type(exc).__name__)
                    if emitted:
                        raise Exception("AI service is temporarily unavailable. Please try again later.") from exc
                    if attempt == 0:
                        await asyncio.sleep(0.35)
            logger.warning("Switching Ojas coach provider after %s failed", provider["name"])
        raise Exception("AI service is temporarily unavailable. Please try again later.") from last_error

    def get_personalized_fallback(
        self,
        user_message: str,
        profile_context: str,
        workout_context: str,
        nutrition_context: str,
    ) -> str:
        """Useful deterministic coaching when the external model is unavailable."""
        message = user_message.lower()
        goal_match = re.search(r"Goal: ([^\n]+)", profile_context)
        experience_match = re.search(r"Experience: ([^\n]+)", profile_context)
        diet_match = re.search(r"Diet: ([^\n]+)", profile_context)
        goal = (goal_match.group(1).replace("_", " ") if goal_match else "your current goal")
        experience = experience_match.group(1) if experience_match else "your current level"
        diet = diet_match.group(1).replace("_", "-") if diet_match else "your saved preference"

        if any(term in message for term in ("workout", "train", "exercise", "today")):
            exercise_lines = [line for line in workout_context.splitlines() if line.startswith("-")][:4]
            if exercise_lines:
                return (
                    f"🏋️ Your next session:\n\nBased on your {goal} goal and {experience} experience, use the workout already saved for today.\n\n"
                    + "\n".join(exercise_lines)
                    + "\n\n✅ Next step:\nStart the first exercise and keep one or two reps in reserve."
                )
            return (
                f"🏋️ Your next move:\n\nYour profile is set for {goal} at {experience} level, but no workout is saved today.\n\n"
                "✅ Next step:\nOpen Workout, choose the time and equipment you have, then ask me to adjust it."
            )

        if any(term in message for term in ("meal", "food", "protein", "diet", "calorie")):
            meals_match = re.search(r"Meals logged: (\d+)", nutrition_context)
            protein_match = re.search(r"Protein: (\d+) g", nutrition_context)
            meals = meals_match.group(1) if meals_match else "0"
            protein = protein_match.group(1) if protein_match else "0"
            return (
                f"🍽️ Personal nutrition check:\n\nYour goal is {goal} and your food preference is {diet}. Today you have {meals} meals and {protein} g protein logged.\n\n"
                "✅ Next step:\nLog your next meal as eaten. I will adjust from the real total instead of guessing."
            )

        return (
            f"I’m coaching around your {goal} goal and {experience} experience.\n\n"
            "I can use your saved profile, today’s workout, nutrition log, and this conversation.\n\n"
            "What should we solve first: movement, food, or recovery?"
        )
    
    async def get_ai_response(
        self, 
        user_message: str, 
        user_id: Optional[str] = None,
        client: Optional[Client] = None,
        fresh_profile_data: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[list[Dict[str, str]]] = None,
    ) -> str:
        """
        Get AI response from DeepSeek API with profile and workout personalization.
        
        System prompt order:
        1. Base system rules (Ojas AI AI Trainer)
        2. User profile context (age, goal, injuries, etc.)
        3. Available workout context (exercise catalog)
        4. User message
        
        Args:
            user_message: User's question/message
            user_id: Optional user ID for personalization
            client: Optional Supabase client for fetching data
            
        Returns:
            AI response text
            
        Raises:
            Exception: If API call fails
        """
        # Build system prompt with optional contexts
        system_prompt = self.BASE_SYSTEM_PROMPT
        profile_context = ""
        workout_context = ""
        nutrition_context = ""

        if fresh_profile_data:
            fresh_context = "\n".join([f"{key}: {value}" for key, value in fresh_profile_data.items()])
            system_prompt += f"\n\nNEW USER DATA FROM THIS MESSAGE:\n{fresh_context}"
        
        if user_id and client:
            # Add profile context (age, goal, injuries, etc.)
            profile_context = self.get_user_profile_context(user_id, client)
            if profile_context:
                system_prompt += profile_context
            
            # Add workout context (available exercises)
            workout_context = self.get_workout_context(user_id, client)
            if workout_context:
                system_prompt += workout_context

            nutrition_context = self.get_nutrition_context(user_id, client)
            if nutrition_context:
                system_prompt += nutrition_context

            meal_history_context = self.get_meal_history_context(user_id, client)
            if meal_history_context:
                system_prompt += meal_history_context

            progress_context = self.get_progress_context(user_id, client)
            if progress_context:
                system_prompt += progress_context

        providers = self._provider_configs()
        if not providers:
            return self.get_personalized_fallback(
                user_message=user_message,
                profile_context=profile_context,
                workout_context=workout_context,
                nutrition_context=nutrition_context,
            )
        
        recent_history = []
        for item in (conversation_history or [])[-8:]:
            role = item.get("role")
            content = str(item.get("content", "")).strip()[:1200]
            if role in {"user", "assistant"} and content:
                recent_history.append({"role": role, "content": content})

        last_error: Optional[Exception] = None
        for provider in providers:
            payload = {
                "model": provider["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    *recent_history,
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.4,
                "max_tokens": 600,
                "stream": False,
            }
            if provider["name"] == "gemini":
                payload["reasoning_effort"] = "none"
            headers = {"Authorization": f"Bearer {provider['key']}", "Content-Type": "application/json"}
            try:
                logger.debug("Calling %s coach model %s", provider["name"], provider["model"])
                async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=8.0)) as client_http:
                    response = await client_http.post(provider["url"], headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                ai_reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if not ai_reply:
                    raise ValueError("Provider returned no coach text")
                self.last_provider = provider["name"]
                return self.sanitize_coach_output(self._format_response_with_line_breaks(ai_reply))
            except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning("%s coach request failed: %s", provider["name"], type(exc).__name__)
                continue
        raise Exception("AI service is temporarily unavailable. Please try again later.") from last_error
