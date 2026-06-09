"""
Credit Service - Manages daily AI credit system for food tracking
Handles credit checking, consumption, and daily reset logic
"""

from datetime import date
from typing import Dict, Any
import logging
from supabase import Client

logger = logging.getLogger(__name__)


class CreditService:
    """Service for managing user AI credits"""
    
    DEFAULT_DAILY_CREDITS = 3
    
    def __init__(self, supabase: Client):
        """
        Initialize credit service
        
        Args:
            supabase: Supabase client instance
        """
        self.supabase = supabase
    
    async def get_or_create_daily_credits(self, user_id: str, today: date = None) -> Dict[str, Any]:
        """
        Get or create credit record for today
        
        Args:
            user_id: User ID
            today: Date to check (defaults to today)
            
        Returns:
            Dict with: credits_used, credits_limit, remaining_credits
        """
        if today is None:
            today = date.today()
        
        today_str = today.isoformat()
        
        try:
            # Try to get existing record
            response = self.supabase.table('user_food_credits').select('*').eq(
                'user_id', user_id
            ).eq(
                'date', today_str
            ).execute()
            
            if response.data and len(response.data) > 0:
                # Record exists
                record = response.data[0]
                credits_used = record['credits_used']
                credits_limit = record['credits_limit']
            else:
                # Create new record for today
                insert_data = {
                    'user_id': user_id,
                    'date': today_str,
                    'credits_used': 0,
                    'credits_limit': self.DEFAULT_DAILY_CREDITS
                }
                
                response = self.supabase.table('user_food_credits').insert(
                    insert_data
                ).execute()
                
                if not response.data or len(response.data) == 0:
                    raise Exception("Failed to create credit record")
                
                record = response.data[0]
                credits_used = 0
                credits_limit = self.DEFAULT_DAILY_CREDITS
                
                logger.info(f"Created new credit record for user {user_id}: {credits_limit} credits")
            
            remaining_credits = max(0, credits_limit - credits_used)
            
            return {
                'credits_used': credits_used,
                'credits_limit': credits_limit,
                'remaining_credits': remaining_credits,
                'date': today_str
            }
            
        except Exception as e:
            logger.error(f"Error getting/creating credits for user {user_id}: {e}")
            # Return default values on error
            return {
                'credits_used': 0,
                'credits_limit': self.DEFAULT_DAILY_CREDITS,
                'remaining_credits': self.DEFAULT_DAILY_CREDITS,
                'date': today_str
            }
    
    async def check_remaining_credits(self, user_id: str) -> int:
        """
        Check how many credits user has remaining today
        
        Args:
            user_id: User ID
            
        Returns:
            Number of remaining credits
        """
        credit_info = await self.get_or_create_daily_credits(user_id)
        return credit_info['remaining_credits']
    
    async def consume_credit(self, user_id: str) -> Dict[str, Any]:
        """
        Consume one credit for the user
        
        Args:
            user_id: User ID
            
        Returns:
            Updated credit info with remaining_credits
            
        Raises:
            ValueError: If no credits remaining
        """
        today = date.today()
        today_str = today.isoformat()
        
        try:
            # Get current credits
            credit_info = await self.get_or_create_daily_credits(user_id, today)
            
            if credit_info['remaining_credits'] <= 0:
                raise ValueError("No credits remaining for today")
            
            # Increment credits_used
            new_credits_used = credit_info['credits_used'] + 1
            
            response = self.supabase.table('user_food_credits').update({
                'credits_used': new_credits_used
            }).eq(
                'user_id', user_id
            ).eq(
                'date', today_str
            ).execute()
            
            if not response.data or len(response.data) == 0:
                raise Exception("Failed to update credit usage")
            
            new_remaining = credit_info['credits_limit'] - new_credits_used
            
            logger.info(f"Consumed 1 credit for user {user_id}. Remaining: {new_remaining}")
            
            return {
                'credits_used': new_credits_used,
                'credits_limit': credit_info['credits_limit'],
                'remaining_credits': new_remaining,
                'date': today_str
            }
            
        except ValueError:
            # Re-raise credit exhausted error
            raise
        except Exception as e:
            logger.error(f"Error consuming credit for user {user_id}: {e}")
            raise Exception(f"Failed to consume credit: {str(e)}")
    
    async def has_credits(self, user_id: str) -> bool:
        """
        Check if user has any credits remaining
        
        Args:
            user_id: User ID
            
        Returns:
            True if user has credits, False otherwise
        """
        remaining = await self.check_remaining_credits(user_id)
        return remaining > 0
