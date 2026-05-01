"""
Crop Recommendation API — AI-powered crop recommendations using Groq.
"""

from fastapi import APIRouter, Query
from typing import Optional
from pydantic import BaseModel

from app.services.crop_recommendation_service import crop_recommendation_service
from app.services.weather_service import weather_service

router = APIRouter()


class RecommendationRequest(BaseModel):
    soil_type: str
    water_availability: str
    previous_crop: Optional[str] = ""
    state: str
    district: str
    land_size: Optional[str] = ""
    farming_type: Optional[str] = "Conventional"


@router.post("/crop-recommendation")
async def get_crop_recommendation(req: RecommendationRequest):
    """
    Get AI crop recommendations based on:
    - Soil type, water availability, previous crop
    - Real-time weather from OpenWeatherMap
    - Current season (auto-detected)
    - Location (state + district)
    """

    # Fetch real-time weather for user's location
    raw_weather = await weather_service.get_weather_by_district_and_state(
        req.district, req.state
    )

    if raw_weather:
        weather = weather_service.parse_weather(raw_weather)
    else:
        # Fallback weather if fetch fails
        weather = {
            "temp": 30, "feels_like": 32, "humidity": 65,
            "condition": "Clear", "description": "clear sky",
            "wind_speed": 10, "rain_1h": 0,
        }

    recommendations = await crop_recommendation_service.get_recommendations(
        soil_type=req.soil_type,
        water_availability=req.water_availability,
        previous_crop=req.previous_crop or "",
        state=req.state,
        district=req.district,
        weather=weather,
        land_size=req.land_size,
        farming_type=req.farming_type,
    )

    return {
        "recommendations": recommendations,
        "weather_used": weather,
        "location": f"{req.district}, {req.state}",
    }
