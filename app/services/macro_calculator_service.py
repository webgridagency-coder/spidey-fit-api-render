"""
Macro Calculator Service - Calculate daily macro targets based on user profile
Auto-calculates: protein, carbs, fats, fiber, steps, calories
"""

import logging
from typing import Dict, Any, Optional
from supabase import Client

logger = logging.getLogger(__name__)


class MacroCalculatorService:
    """
    Calculate daily macro targets based on user profile.
    
    Calculations based on:
    - Goal (fat loss, muscle gain, recomposition, overall fitness)
    - Weight
    - Activity level
    - Experience level
    
    Automatically updates user_profile when changes detected.
    """
    
    # Protein multipliers (grams per kg of body weight)
    # SOURCE DOCUMENT: fat_loss/recomposition → 2.0-2.2, muscle_gain → 1.6-2.0
    PROTEIN_MULTIPLIERS = {
        "Fat Loss": 2.2,  # High protein to preserve muscle during deficit
        "Muscle Gain": 1.8,  # 1.6-2.0 range (using 1.8 as middle ground)
        "Muscle Recomposition": 2.2,  # High protein for both goals
        "Overall Fitness": 1.8,  # Moderate protein
    }
    
    # Activity level multipliers for TDEE calculation
    ACTIVITY_MULTIPLIERS = {
        "Sedentary": 1.2,  # Little to no exercise
        "Light": 1.375,  # 1-3 days/week
        "Moderate": 1.55,  # 3-5 days/week
        "Very Active": 1.725,  # 6-7 days/week
    }
    
    # Calorie adjustments based on goal (relative to TDEE)
    # SOURCE DOCUMENT: fat_loss → -500, recomposition → -200, muscle_gain → +250
    CALORIE_ADJUSTMENTS = {
        "Fat Loss": -500,  # 500 calorie deficit
        "Muscle Gain": +250,  # 250 calorie surplus (SOURCE DOCUMENT)
        "Muscle Recomposition": -200,  # Slight deficit
        "Overall Fitness": 0,  # Maintenance
    }
    
    # Step targets based on goal
    # SOURCE DOCUMENT: fat_loss → 10k, recomposition → 8-8.5k, muscle_gain → 7k
    STEP_TARGETS = {
        "Fat Loss": 10000,  # Higher for fat loss
        "Muscle Gain": 7000,  # Lower for muscle gain (recovery priority)
        "Muscle Recomposition": 8000,  # 8-8.5k range (using 8k)
        "Overall Fitness": 8000,  # General health
    }
    
    def calculate_bmr(self, weight_kg: float, height_cm: int, age: int, gender: str) -> int:
        """
        Calculate Basal Metabolic Rate (BMR) using Mifflin-St Jeor Equation.
        
        Args:
            weight_kg: Weight in kilograms (can be decimal)
            height_cm: Height in centimeters
            age: Age in years
            gender: "Male", "Female", or "Other"
            
        Returns:
            BMR in calories/day
        """
        # Mifflin-St Jeor Equation
        if gender and gender.lower() == "male":
            bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
        else:
            # Female or Other (use female formula as default)
            bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
        
        return int(bmr)
    
    def calculate_tdee(self, bmr: int, activity_level: str) -> int:
        """
        Calculate Total Daily Energy Expenditure (TDEE).
        
        Args:
            bmr: Basal Metabolic Rate
            activity_level: Activity level string
            
        Returns:
            TDEE in calories/day
        """
        multiplier = self.ACTIVITY_MULTIPLIERS.get(activity_level, 1.2)
        return int(bmr * multiplier)
    
    def calculate_macros(
        self,
        weight_kg: float,
        height_cm: Optional[int],
        age: Optional[int],
        gender: Optional[str],
        goal: str,
        activity_level: Optional[str]
    ) -> Dict[str, int]:
        """
        Calculate all macro targets.
        
        Args:
            weight_kg: Weight in kg (can be decimal)
            height_cm: Height in cm (optional for basic calculations)
            age: Age in years (optional for basic calculations)
            gender: Gender (optional for basic calculations)
            goal: Fitness goal
            activity_level: Activity level (optional, defaults to "Moderate")
            
        Returns:
            Dictionary with macro targets: protein, carbs, fats, fiber, steps, calories
        """
        macros = {}
        
        # PROTEIN (always calculate, based on weight and goal)
        protein_multiplier = self.PROTEIN_MULTIPLIERS.get(goal, 2.0)
        macros["protein_target"] = int(weight_kg * protein_multiplier)
        
        # STEPS (based on goal)
        macros["step_target"] = self.STEP_TARGETS.get(goal, 8000)
        
        # FIBER (general recommendation)
        macros["fiber_target"] = 30  # 25-35g is healthy range
        
        # CALORIES (requires BMR calculation if height/age/gender available)
        if height_cm and age and gender:
            bmr = self.calculate_bmr(weight_kg, height_cm, age, gender)
            activity = activity_level or "Moderate"
            tdee = self.calculate_tdee(bmr, activity)
            calorie_adjustment = self.CALORIE_ADJUSTMENTS.get(goal, 0)
            macros["calories_target"] = tdee + calorie_adjustment
            
            # CARBS and FATS (calculated from calories and protein)
            protein_calories = macros["protein_target"] * 4  # 4 cal/g protein
            remaining_calories = macros["calories_target"] - protein_calories
            
            # Fat provides 9 cal/g, carbs provide 4 cal/g
            # Typical split: 25-30% fat, rest carbs
            fat_calories = int(remaining_calories * 0.28)  # 28% from fat
            carb_calories = remaining_calories - fat_calories
            
            macros["fats_target"] = int(fat_calories / 9)
            macros["carbs_target"] = int(carb_calories / 4)
        else:
            # Basic calculation without full TDEE
            # Estimate based on weight and goal
            estimated_calories = weight_kg * 30  # Rough estimate
            calorie_adjustment = self.CALORIE_ADJUSTMENTS.get(goal, 0)
            macros["calories_target"] = estimated_calories + calorie_adjustment
            
            protein_calories = macros["protein_target"] * 4
            remaining_calories = macros["calories_target"] - protein_calories
            
            fat_calories = int(remaining_calories * 0.28)
            carb_calories = remaining_calories - fat_calories
            
            macros["fats_target"] = int(fat_calories / 9)
            macros["carbs_target"] = int(carb_calories / 4)
        
        logger.info(f"✅ Calculated macros for {weight_kg}kg, goal: {goal}")
        logger.debug(f"   Protein: {macros['protein_target']}g, Carbs: {macros['carbs_target']}g, Fats: {macros['fats_target']}g")
        logger.debug(f"   Calories: {macros['calories_target']}, Steps: {macros['step_target']}")
        
        return macros
    
    async def update_user_macros(
        self,
        user_id: str,
        client: Client
    ) -> bool:
        """
        Fetch user profile, calculate macros, and update database.
        
        Args:
            user_id: User's UUID
            client: Supabase client (service_role to bypass RLS)
            
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            # Fetch current profile
            response = client.table("user_profile").select(
                "weight_kg, height_cm, age, gender, goal, activity_level"
            ).eq("user_id", user_id).execute()
            
            if not response.data or len(response.data) == 0:
                logger.debug(f"No profile found for user {user_id[:8]}...")
                return False
            
            profile = response.data[0]
            
            # Check if we have minimum required data
            if not profile.get("weight_kg") or not profile.get("goal"):
                logger.debug(f"Insufficient data for macro calculation (need weight and goal)")
                return False
            
            # Calculate macros
            macros = self.calculate_macros(
                weight_kg=profile["weight_kg"],
                height_cm=profile.get("height_cm"),
                age=profile.get("age"),
                gender=profile.get("gender"),
                goal=profile["goal"],
                activity_level=profile.get("activity_level")
            )
            
            # Update user profile with calculated macros
            client.table("user_profile").update(macros).eq("user_id", user_id).execute()
            
            logger.info(f"✅ Updated macros for user {user_id[:8]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update macros: {type(e).__name__}: {str(e)}")
            return False
