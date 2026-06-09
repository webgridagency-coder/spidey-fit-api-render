"""
Profile Extractor Service - Auto-extract user profile data from conversational messages
Uses OpenRouter AI to parse natural language and save to user_profile table
"""

import json
import httpx
import logging
from typing import Dict, Any
from supabase import Client

from app.config import settings

logger = logging.getLogger(__name__)


class ProfileExtractorService:
    """
    Extract user profile data from conversational messages using AI.
    Saves extracted data to user_profile table automatically.
    """
    
    EXTRACTION_PROMPT = """You are a fitness profile data extractor. Extract ONLY the following data from the user's message and return as JSON:

{{
  "weight_kg": <integer or null>,
  "height_cm": <integer or null>,
  "body_fat_percentage": <decimal or null>,
  "age": <integer or null>,
  "gender": <"Male" | "Female" | "Other" or null>,
  "goal": <"Fat Loss" | "Muscle Gain" | "Muscle Recomposition" | "Overall Fitness" or null>,
  "experience_level": <"Beginner" | "Intermediate" | "Advanced" or null>,
  "diet_preference": <"Indian" | "Any cuisine" or null>,
  "activity_level": <"Sedentary" | "Light" | "Moderate" | "Very Active" or null>,
  "goal_target_weight": <integer or null>,
  "goal_duration_days": <integer or null>,
  "challenge_duration_days": <integer or null>,
  "is_challenge_start": <boolean or null>
}}

Rules:
- Return ONLY valid JSON (no extra text, no markdown)
- Use exact enum values shown above
- If value not mentioned, use null
- Infer values intelligently: "any food" → "Any cuisine", "recomp" → "Muscle Recomposition"
- Weight: 40-200kg, Height: 100-250cm, Body fat: 5-50%
- Map similar terms: "beginner/newbie" → "Beginner", "experienced" → "Intermediate", "expert/pro" → "Advanced"
- Goal timeframe extraction:
  * "lose 5kg in 2 months" → goal_target_weight: (current_weight - 5), goal_duration_days: 60
  * "reach 75kg in 3 months" → goal_target_weight: 75, goal_duration_days: 90
  * "gain 10kg in 6 months" → goal_target_weight: (current_weight + 10), goal_duration_days: 180
- Challenge detection:
  * "Day 1", "start challenge", "begin challenge" → is_challenge_start: true
  * "30 days challenge", "45 day challenge", "60-day challenge" → challenge_duration_days: 30/45/60
  * "lose 15kg in 60 days" → challenge_duration_days: 60 (if it's a specific commitment)

User message: "{user_message}"

Return JSON:"""
    
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.api_url = f"{settings.OPENROUTER_BASE_URL}/chat/completions"
        self.model = settings.OPENROUTER_MODEL
    
    async def extract_profile_data(self, user_message: str) -> Dict[str, Any]:
        """
        Extract profile data from user message using AI.
        
        Args:
            user_message: User's conversational message
            
        Returns:
            Dictionary with extracted profile fields (only non-null values)
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": self.EXTRACTION_PROMPT.format(user_message=user_message)
                    }
                ],
                "temperature": 0.1,  # Very low for consistent extraction
                "max_tokens": 250
            }
            
            logger.debug(f"Extracting profile data from message...")
            
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
                
                if response.status_code != 200:
                    logger.warning(f"Profile extraction failed: {response.status_code}")
                    return {}
                
                data = response.json()
                ai_response = data["choices"][0]["message"]["content"].strip()
                
                # Remove markdown code blocks if present
                if ai_response.startswith("```"):
                    ai_response = ai_response.split("```")[1]
                    if ai_response.startswith("json"):
                        ai_response = ai_response[4:]
                    ai_response = ai_response.strip()
                
                # Parse JSON response
                extracted_data = json.loads(ai_response)
                
                # Filter out null values and validate
                profile_data = {}
                for key, value in extracted_data.items():
                    if value is not None:
                        # Validate ranges
                        if key == "weight_kg" and (value < 40 or value > 200):
                            logger.warning(f"Invalid weight: {value}kg, skipping")
                            continue
                        if key == "height_cm" and (value < 100 or value > 250):
                            logger.warning(f"Invalid height: {value}cm, skipping")
                            continue
                        if key == "body_fat_percentage" and (value < 5 or value > 50):
                            logger.warning(f"Invalid body fat: {value}%, skipping")
                            continue
                        if key == "age" and (value < 13 or value > 100):
                            logger.warning(f"Invalid age: {value}, skipping")
                            continue
                        
                        profile_data[key] = value
                
                if profile_data:
                    logger.info(f"✅ Extracted profile data: {list(profile_data.keys())}")
                else:
                    logger.debug("No profile data found in message")
                
                return profile_data
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction JSON: {str(e)}")
            return {}
        except Exception as e:
            logger.error(f"Profile extraction error: {type(e).__name__}: {str(e)}")
            return {}
    
    async def save_profile_data(
        self,
        user_id: str,
        profile_data: Dict[str, Any],
        client: Client
    ) -> bool:
        """
        Save extracted profile data to user_profile table.
        
        Args:
            user_id: User's UUID
            profile_data: Extracted profile fields
            client: Supabase client (service_role to bypass RLS)
            
        Returns:
            True if saved successfully, False otherwise
        """
        if not profile_data:
            return False
        
        try:
            # Check if profile exists
            response = client.table("user_profile").select("user_id, weight_kg").eq("user_id", user_id).execute()
            
            # If goal tracking fields are present, set start date and starting weight
            if "goal_target_weight" in profile_data or "goal_duration_days" in profile_data:
                from datetime import datetime
                
                # Set goal start date if not already set
                if "goal_start_date" not in profile_data:
                    profile_data["goal_start_date"] = datetime.now().date().isoformat()
                
                # Set starting weight if not already set (use current weight)
                if "starting_weight" not in profile_data and response.data and len(response.data) > 0:
                    current_weight = response.data[0].get("weight_kg")
                    if current_weight:
                        profile_data["starting_weight"] = current_weight
                elif "starting_weight" not in profile_data and "weight_kg" in profile_data:
                    profile_data["starting_weight"] = profile_data["weight_kg"]
            
            # If challenge start detected, set challenge_start_date to today
            if profile_data.get("is_challenge_start"):
                from datetime import datetime
                profile_data["challenge_start_date"] = datetime.now().date().isoformat()
                # Remove the flag, we only need the date
                del profile_data["is_challenge_start"]
                logger.info(f"✅ Challenge started for user {user_id[:8]}...")
            
            if response.data and len(response.data) > 0:
                # Update existing profile (merge new data with existing)
                client.table("user_profile").update(profile_data).eq("user_id", user_id).execute()
                logger.info(f"✅ Updated profile for user {user_id[:8]}... with fields: {list(profile_data.keys())}")
            else:
                # Insert new profile
                profile_data["user_id"] = user_id
                client.table("user_profile").insert(profile_data).execute()
                logger.info(f"✅ Created profile for user {user_id[:8]}... with fields: {list(profile_data.keys())}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save profile: {type(e).__name__}: {str(e)}")
            return False
    
    async def extract_and_save(
        self,
        user_message: str,
        user_id: str,
        client: Client
    ) -> Dict[str, Any]:
        """
        Extract profile data from message and save to database.
        
        Args:
            user_message: User's conversational message
            user_id: User's UUID
            client: Supabase client (service_role)
            
        Returns:
            Dictionary of extracted data (empty if extraction failed)
        """
        # Step 1: Extract data using AI
        profile_data = await self.extract_profile_data(user_message)
        
        # Step 2: Save to database if any data extracted
        if profile_data:
            success = await self.save_profile_data(user_id, profile_data, client)
            if not success:
                logger.warning("Profile extraction succeeded but save failed")
                return {}
        
        return profile_data
