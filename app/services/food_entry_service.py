"""
Food Entry Service - Manages food entry persistence and nutrition aggregation
Handles saving entries and calculating daily totals
"""

from datetime import date
from typing import Dict, Any, List
import logging
from supabase import Client
from decimal import Decimal
import json

logger = logging.getLogger(__name__)


class FoodEntryService:
    """Service for managing food entries"""
    
    def __init__(self, supabase: Client):
        """
        Initialize food entry service
        
        Args:
            supabase: Supabase client instance
        """
        self.supabase = supabase
    
    async def save_food_entry(
        self,
        user_id: str,
        meal_type: str,
        calories: float,
        protein: float,
        carbs: float,
        fats: float,
        fiber: float,
        source: str,
        micronutrients: Dict[str, float] | None = None,
        confidence_note: str = None,
        description: str = None,
        entry_date: date = None
    ) -> Dict[str, Any]:
        """
        Save a food entry to the database
        
        Args:
            user_id: User ID
            meal_type: breakfast, lunch, dinner, or snacks
            calories: Calorie count
            protein: Protein in grams
            carbs: Carbs in grams
            fats: Fats in grams
            fiber: Fiber in grams
            source: ai_text, ai_image, or manual
            confidence_note: Optional AI confidence note
            description: Optional food description
            entry_date: Date of entry (defaults to today)
            
        Returns:
            Saved entry record
            
        Raises:
            ValueError: If validation fails
            Exception: If save fails
        """
        if entry_date is None:
            entry_date = date.today()
        
        # Validate meal_type
        valid_meal_types = ['breakfast', 'lunch', 'dinner', 'snacks']
        if meal_type not in valid_meal_types:
            raise ValueError(f"Invalid meal_type. Must be one of: {', '.join(valid_meal_types)}")
        
        # Validate source
        valid_sources = ['ai_text', 'ai_image', 'manual']
        if source not in valid_sources:
            raise ValueError(f"Invalid source. Must be one of: {', '.join(valid_sources)}")
        
        try:
            # Prepare entry data
            entry_data = {
                'user_id': user_id,
                'date': entry_date.isoformat(),
                'meal_type': meal_type,
                'calories': float(calories),
                'protein': float(protein),
                'carbs': float(carbs),
                'fats': float(fats),
                'fiber': float(fiber),
                'source': source,
                'confidence_note': self._pack_note(confidence_note, micronutrients),
                'description': description
            }
            
            # Insert into database
            response = self.supabase.table('food_entries').insert(entry_data).execute()
            
            if not response.data or len(response.data) == 0:
                raise Exception("Failed to save food entry")
            
            saved_entry = response.data[0]
            
            logger.info(f"Saved food entry for user {user_id}: {meal_type}, {calories} cal")
            
            return saved_entry
            
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(f"Error saving food entry for user {user_id}: {e}")
            raise Exception(f"Failed to save food entry: {str(e)}")
    
    async def get_daily_nutrition_totals(self, user_id: str, entry_date: date = None) -> Dict[str, float]:
        """
        Get aggregated nutrition totals for a specific date
        
        Args:
            user_id: User ID
            entry_date: Date to aggregate (defaults to today)
            
        Returns:
            Dict with: calories, protein, carbs, fats, fiber
        """
        if entry_date is None:
            entry_date = date.today()
        
        date_str = entry_date.isoformat()
        
        try:
            # Query all entries for this user and date
            response = self.supabase.table('food_entries').select(
                'calories, protein, carbs, fats, fiber, confidence_note'
            ).eq(
                'user_id', user_id
            ).eq(
                'date', date_str
            ).execute()
            
            # Calculate totals
            totals = {
                'calories': 0.0,
                'protein': 0.0,
                'carbs': 0.0,
                'fats': 0.0,
                'fiber': 0.0,
                'sodium_mg': 0.0,
                'potassium_mg': 0.0,
                'calcium_mg': 0.0,
                'iron_mg': 0.0,
                'vitamin_c_mg': 0.0,
            }
            
            if response.data:
                for entry in response.data:
                    totals['calories'] += float(entry.get('calories', 0))
                    totals['protein'] += float(entry.get('protein', 0))
                    totals['carbs'] += float(entry.get('carbs', 0))
                    totals['fats'] += float(entry.get('fats', 0))
                    totals['fiber'] += float(entry.get('fiber', 0))
                    _, micros = self._unpack_note(entry.get('confidence_note'))
                    for key in self.MICRO_KEYS:
                        totals[key] += micros[key]
            
            logger.info(f"Calculated daily totals for user {user_id} on {date_str}: {totals['calories']} cal")
            
            return totals
            
        except Exception as e:
            logger.error(f"Error getting daily totals for user {user_id}: {e}")
            # Return zeros on error
            return {
                'calories': 0.0,
                'protein': 0.0,
                'carbs': 0.0,
                'fats': 0.0,
                'fiber': 0.0,
                'sodium_mg': 0.0,
                'potassium_mg': 0.0,
                'calcium_mg': 0.0,
                'iron_mg': 0.0,
                'vitamin_c_mg': 0.0,
            }
    
    async def get_today_entries(self, user_id: str, entry_date: date = None) -> List[Dict[str, Any]]:
        """
        Get all food entries for today
        
        Args:
            user_id: User ID
            entry_date: Date to fetch (defaults to today)
            
        Returns:
            List of food entry records
        """
        if entry_date is None:
            entry_date = date.today()
        
        date_str = entry_date.isoformat()
        
        try:
            response = self.supabase.table('food_entries').select('*').eq(
                'user_id', user_id
            ).eq(
                'date', date_str
            ).order('created_at', desc=False).execute()
            
            entries = response.data if response.data else []
            for entry in entries:
                clean_note, micros = self._unpack_note(entry.get('confidence_note'))
                entry['confidence_note'] = clean_note
                entry['micronutrients'] = micros
            
            logger.info(f"Retrieved {len(entries)} food entries for user {user_id} on {date_str}")
            
            return entries
            
        except Exception as e:
            logger.error(f"Error getting today's entries for user {user_id}: {e}")
            return []
    
    async def get_meal_entries(self, user_id: str, meal_type: str, entry_date: date = None) -> List[Dict[str, Any]]:
        """
        Get all entries for a specific meal type
        
        Args:
            user_id: User ID
            meal_type: breakfast, lunch, dinner, or snacks
            entry_date: Date to fetch (defaults to today)
            
        Returns:
            List of food entry records for that meal
        """
        if entry_date is None:
            entry_date = date.today()
        
        date_str = entry_date.isoformat()
        
        try:
            response = self.supabase.table('food_entries').select('*').eq(
                'user_id', user_id
            ).eq(
                'date', date_str
            ).eq(
                'meal_type', meal_type
            ).order('created_at', desc=False).execute()
            
            entries = response.data if response.data else []
            
            return entries
            
        except Exception as e:
            logger.error(f"Error getting meal entries for user {user_id}, meal {meal_type}: {e}")
            return []
    
    async def delete_entry(self, user_id: str, entry_id: str) -> bool:
        """
        Delete a specific food entry
        
        Args:
            user_id: User ID (for security check)
            entry_id: Entry ID to delete
            
        Returns:
            True if deleted successfully
        """
        try:
            response = self.supabase.table('food_entries').delete().eq(
                'id', entry_id
            ).eq(
                'user_id', user_id  # Ensure user can only delete their own entries
            ).execute()
            
            if response.data:
                logger.info(f"Deleted food entry {entry_id} for user {user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting entry {entry_id} for user {user_id}: {e}")
            return False
    MICRO_PREFIX = "__OJAS_MICROS__"
    MICRO_KEYS = ("sodium_mg", "potassium_mg", "calcium_mg", "iron_mg", "vitamin_c_mg")

    @classmethod
    def _pack_note(cls, note: str | None, micronutrients: Dict[str, float] | None) -> str | None:
        micros = {key: max(0.0, float((micronutrients or {}).get(key, 0) or 0)) for key in cls.MICRO_KEYS}
        return f"{cls.MICRO_PREFIX}{json.dumps(micros, separators=(',', ':'))}\n{note or ''}".strip()

    @classmethod
    def _unpack_note(cls, note: str | None) -> tuple[str | None, Dict[str, float]]:
        text = str(note or "")
        micros = {key: 0.0 for key in cls.MICRO_KEYS}
        if text.startswith(cls.MICRO_PREFIX):
            payload, _, clean = text[len(cls.MICRO_PREFIX):].partition("\n")
            try:
                decoded = json.loads(payload)
                micros = {key: max(0.0, float(decoded.get(key, 0) or 0)) for key in cls.MICRO_KEYS}
                return clean or None, micros
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
        return note, micros
