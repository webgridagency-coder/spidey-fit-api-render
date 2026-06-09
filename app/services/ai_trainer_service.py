"""
AI Trainer service - OpenRouter integration (DeepSeek via OpenRouter)
Handles AI chat interactions with strict fitness coaching prompt
Includes user profile and workout catalog personalization
"""

import httpx
import logging
import re
from typing import Dict, Any, Optional
from supabase import Client

from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)


class AITrainerService:
    """Service for AI trainer interactions via OpenRouter (DeepSeek model)"""
    
    # Advanced AI Fitness & Nutrition Coach System Prompt
    BASE_SYSTEM_PROMPT = """You are a real human fitness coach. Act calm, practical, and human.

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
    
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.api_url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
        self.model = settings.OPENROUTER_MODEL
        self.timeout = min(settings.OPENROUTER_TIMEOUT, 12)

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
    
    async def get_user_profile_context(self, user_id: str, client: Client) -> str:
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
    
    async def get_workout_context(self, user_id: str, client: Client) -> str:
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
                "muscle, exercises"
            ).eq("user_id", user_id).eq("date", today).execute()
            
            # If no workout today, get the most recent workout
            if not response.data or len(response.data) == 0:
                response = client.table("workouts").select(
                    "muscle, exercises"
                ).eq("user_id", user_id).order(
                    "date", desc=True
                ).limit(1).execute()
            
            # No workouts found at all
            if not response.data or len(response.data) == 0:
                logger.debug(f"No workouts found for user {user_id[:8]}...")
                return ""
            
            workout = response.data[0]
            muscle_group = workout.get("muscle", "Unknown")
            exercises = workout.get("exercises", [])
            
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
            context = f"\n\nAVAILABLE WORKOUTS TODAY:\nMuscle Group: {muscle_group}\nExercises:\n"
            context += "\n".join([f"- {name}" for name in exercise_names])
            
            return context
            
        except Exception as e:
            # If workout fetch fails, continue without workout context (graceful degradation)
            logger.warning(f"Failed to fetch workout for user {user_id[:8]}...: {str(e)}")
            return ""
    
    async def get_ai_response(
        self, 
        user_message: str, 
        user_id: Optional[str] = None,
        client: Optional[Client] = None,
        fresh_profile_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Get AI response from DeepSeek API with profile and workout personalization.
        
        System prompt order:
        1. Base system rules (Spider-Fit AI Trainer)
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

        if fresh_profile_data:
            fresh_context = "\n".join([f"{key}: {value}" for key, value in fresh_profile_data.items()])
            system_prompt += f"\n\nNEW USER DATA FROM THIS MESSAGE:\n{fresh_context}"
        
        if user_id and client:
            # Add profile context (age, goal, injuries, etc.)
            profile_context = await self.get_user_profile_context(user_id, client)
            if profile_context:
                system_prompt += profile_context
            
            # Add workout context (available exercises)
            workout_context = await self.get_workout_context(user_id, client)
            if workout_context:
                system_prompt += workout_context
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            "temperature": 0.4,  # Lower temp for better instruction following (formatting)
            "max_tokens": 170,
            "stream": False
        }
        
        try:
            logger.debug(f"Calling OpenRouter API with model: {self.model}")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client_http:
                response = await client_http.post(
                    self.api_url,
                    headers=headers,
                    json=payload
                )
                
                # Check for API errors
                if response.status_code != 200:
                    error_detail = response.text
                    logger.warning(f"OpenRouter API error: {response.status_code} - {error_detail}")
                    raise Exception("AI service is temporarily unavailable. Please try again later.")
                
                data = response.json()
                
                # Extract AI response
                if "choices" in data and len(data["choices"]) > 0:
                    ai_reply = data["choices"][0]["message"]["content"]
                    logger.debug("OpenRouter response received successfully")
                    
                    # POST-PROCESSING: Force proper line breaks for emoji sections
                    # This fixes the AI's tendency to write everything in one paragraph
                    ai_reply = self._format_response_with_line_breaks(ai_reply)
                    
                    return ai_reply.strip()
                else:
                    logger.warning("OpenRouter returned no choices")
                    raise Exception("AI service is temporarily unavailable. Please try again later.")
                    
        except httpx.TimeoutException:
            logger.warning("OpenRouter request timed out")
            raise Exception("AI service is temporarily unavailable. Please try again later.")
        except httpx.RequestError as e:
            logger.warning(f"OpenRouter network error: {type(e).__name__}")
            raise Exception("AI service is temporarily unavailable. Please try again later.")
        except Exception as e:
            # If already our custom message, pass through
            if "temporarily unavailable" in str(e):
                raise
            # Otherwise, log and return generic message
            logger.error(f"OpenRouter unexpected error: {type(e).__name__}: {str(e)}")
            raise Exception("AI service is temporarily unavailable. Please try again later.")
