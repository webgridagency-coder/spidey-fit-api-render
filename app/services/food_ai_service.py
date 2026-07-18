"""
Food AI Service - Gemini Flash Integration
Handles food nutrition estimation via text description and image analysis
"""

import httpx
import logging
import json
import base64
from typing import Dict, Any, Optional

from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)


class FoodAIService:
    """Service for food nutrition estimation using Gemini Flash"""
    
    # System prompt for Gemini Flash
    NUTRITION_PROMPT = """You are a nutrition estimation assistant.
Estimate calories, protein (g), carbs (g), and fats (g) for the given food.
Be conservative and realistic in your estimates.
If uncertain, estimate slightly lower rather than higher.
Always include a short confidence note explaining the basis of your estimate.

Examples of confidence notes:
- "Estimated based on typical portion size. Please adjust if needed."
- "Based on standard restaurant serving. Actual calories may vary."
- "Approximation for homemade preparation. Adjust for ingredients used."

Return ONLY valid JSON in this exact format:
{
  "food_description": "short specific name of the food and visible portion",
  "calories": number,
  "protein": number,
  "carbs": number,
  "fats": number,
  "confidence_note": "string"
}

Do not include any text outside the JSON object."""

    def __init__(self):
        """Initialize the Food AI service"""
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your-gemini-api-key-here":
            raise ValueError(
                "GEMINI_API_KEY is not configured. "
                "Please set a valid Gemini API key in your .env file."
            )
        
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.timeout = settings.GEMINI_TIMEOUT
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
    
    async def estimate_from_text(self, description: str) -> Dict[str, Any]:
        """
        Estimate nutrition from text description
        
        Args:
            description: Text description of the food
            
        Returns:
            Dictionary containing calories, protein, carbs, fats, and confidence_note
            
        Raises:
            httpx.HTTPError: If API call fails
            ValueError: If response parsing fails
        """
        logger.info(f"Estimating nutrition from text: {description[:50]}...")
        
        try:
            # Use longer timeout for API calls
            timeout = httpx.Timeout(60.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Prepare the request
                prompt = f"{self.NUTRITION_PROMPT}\n\nFood description: {description}"
                
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": prompt
                        }]
                    }],
                    "generationConfig": {
                        "temperature": 0.3,  # Lower temperature for more consistent results
                        "maxOutputTokens": 2048,  # Higher limit to account for thinking tokens in Gemini 2.5
                        "topP": 0.8,
                        "topK": 10,
                        "responseMimeType": "application/json"
                    }
                }
                
                # Make API call
                response = await client.post(
                    f"{self.api_url}?key={self.api_key}",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Extract and parse the response
                result = self._parse_gemini_response(data)
                logger.info(f"Successfully estimated nutrition: {result['calories']} kcal")
                return result
                
        except httpx.TimeoutException:
            logger.error("Gemini API timeout")
            raise httpx.HTTPError("AI analysis timed out. Please try again.")
        except httpx.HTTPError as e:
            logger.error(f"Gemini API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in text estimation: {e}")
            raise ValueError(f"Failed to process nutrition estimation: {str(e)}")
    
    async def estimate_from_image(self, image_bytes: bytes, mime_type: str = "image/jpeg", portion_hint: str = "") -> Dict[str, Any]:
        """
        Estimate nutrition from food image
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Dictionary containing calories, protein, carbs, fats, and confidence_note
            
        Raises:
            httpx.HTTPError: If API call fails
            ValueError: If response parsing fails
        """
        logger.info(f"Estimating nutrition from image ({len(image_bytes)} bytes)")
        
        try:
            # Convert image to base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            logger.info(f"Base64 encoded image size: {len(image_base64)} chars")
            
            # Use longer timeout for image processing
            timeout = httpx.Timeout(90.0, connect=10.0)  # 90 seconds for image processing
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Prepare the request with image
                payload = {
                    "contents": [{
                        "parts": [
                            {
                                "text": self.NUTRITION_PROMPT + "\n\nAnalyze the food in this image and provide nutrition estimates. "
                                + (f"The user supplied this portion/ingredient reference: {portion_hint[:240]}" if portion_hint else "Use visible serving size and clearly state uncertainty.")
                            },
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": image_base64
                                }
                            }
                        ]
                    }],
                    "generationConfig": {
                        "temperature": 0.3,
                        "maxOutputTokens": 2048,  # Higher limit to account for thinking tokens in Gemini 2.5
                        "topP": 0.8,
                        "topK": 10,
                        "responseMimeType": "application/json"
                    }
                }
                
                logger.info("Sending request to Gemini API...")
                # Make API call
                response = await client.post(
                    f"{self.api_url}?key={self.api_key}",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                logger.info(f"Gemini API response status: {response.status_code}")
                
                response.raise_for_status()
                data = response.json()
                
                # Extract and parse the response
                result = self._parse_gemini_response(data)
                logger.info(f"Successfully estimated nutrition from image: {result['calories']} kcal")
                return result
                
        except httpx.TimeoutException:
            logger.error("Gemini API timeout")
            raise httpx.HTTPError("AI analysis timed out. Please try again.")
        except httpx.HTTPError as e:
            logger.error(f"Gemini API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in image estimation: {e}")
            raise ValueError(f"Failed to process image: {str(e)}")
    
    def _parse_gemini_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Gemini API response and extract nutrition data
        
        Args:
            data: Raw API response
            
        Returns:
            Parsed nutrition data
            
        Raises:
            ValueError: If parsing fails
        """
        try:
            # Extract the text from Gemini response
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates in Gemini response")
            
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                raise ValueError("No parts in response content")
            
            text = parts[0].get("text", "")
            
            # Try to extract JSON from the response
            # Sometimes the model includes markdown code blocks
            text = text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            nutrition_data = json.loads(text)
            
            # Validate required fields
            required_fields = ["calories", "protein", "carbs", "fats", "confidence_note"]
            for field in required_fields:
                if field not in nutrition_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Ensure numeric values
            nutrition_data["calories"] = float(nutrition_data["calories"])
            nutrition_data["protein"] = float(nutrition_data["protein"])
            nutrition_data["carbs"] = float(nutrition_data["carbs"])
            nutrition_data["fats"] = float(nutrition_data["fats"])
            
            # Ensure confidence_note is a string
            nutrition_data["confidence_note"] = str(nutrition_data["confidence_note"])
            nutrition_data["food_description"] = str(
                nutrition_data.get("food_description") or "Recognized meal"
            ).strip()[:300]
            
            return nutrition_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Gemini: {e}. Response text: {text[:200]}")
            # Return fallback response
            return {
                "food_description": "Meal requiring review",
                "calories": 250,
                "protein": 10,
                "carbs": 30,
                "fats": 10,
                "confidence_note": "AI analysis was unclear. These are conservative estimates. Please adjust based on your knowledge."
            }
        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}")
            raise ValueError(f"Failed to parse nutrition data: {str(e)}")
