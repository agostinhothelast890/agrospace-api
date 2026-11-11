from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.farms import get_db

router = APIRouter(prefix="/api/farms", tags=["weather"])

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_farm_with_coords(db, farm_id: UUID) -> dict:
    result = (
        db.table("farms")
        .select("id,name,crop,latitude,longitude")
        .eq("id", str(farm_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Farm not found")
    farm = result.data[0]
    if farm["latitude"] is None or farm["longitude"] is None:
        raise HTTPException(status_code=400, detail="Farm has no coordinates")
    return farm


def fetch_weather(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "past_days": 7,
        "forecast_days": 3,
        "timezone": "auto",
    }
    try:
        response = httpx.get(OPEN_METEO_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Weather service unavailable")

    daily = data["daily"]
    current = data["current"]

    # First 7 days are the past week; the last 3 are today + forecast.
    rainfall_7d = round(sum(r or 0 for r in daily["precipitation_sum"][:7]), 1)
    forecast = [
        {"date": d, "temp_max_c": tmax, "temp_min_c": tmin, "rain_mm": rain}
        for d, tmax, tmin, rain in zip(
            daily["time"][7:],
            daily["temperature_2m_max"][7:],
            daily["temperature_2m_min"][7:],
            daily["precipitation_sum"][7:],
        )
    ]

    return {
        "source": "Open-Meteo",
        "current": {
            "temperature_c": current["temperature_2m"],
            "humidity_pct": current["relative_humidity_2m"],
            "rain_mm": current["precipitation"],
        },
        "rainfall_mm_7d": rainfall_7d,
        "forecast": forecast,
    }


@router.get("/{farm_id}/weather")
def farm_weather(farm_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    farm = get_farm_with_coords(db, farm_id)
    weather = fetch_weather(farm["latitude"], farm["longitude"])
    return {"farm": {"id": farm["id"], "name": farm["name"]}, **weather}
