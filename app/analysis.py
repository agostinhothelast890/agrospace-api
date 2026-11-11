from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.farms import get_db
from app.weather import fetch_weather, get_farm_with_coords

router = APIRouter(prefix="/api/farms", tags=["analysis"])

DISCLAIMER = (
    "Demonstration rules based on weather only. "
    "Not agronomic advice; consult an agronomist."
)

# Demo ranges: ideal temperature (°C) and rain in the last 7 days (mm).
CROP_RANGES = {
    "maize": {"temp": (18, 32), "rain_7d": (15, 60)},
    "cassava": {"temp": (20, 35), "rain_7d": (10, 50)},
    "beans": {"temp": (15, 28), "rain_7d": (10, 40)},
    "tomato": {"temp": (18, 30), "rain_7d": (10, 40)},
}
DEFAULT_RANGE = {"temp": (15, 32), "rain_7d": (10, 60)}


def make_factor(name: str, value, status: str, message: str) -> dict:
    return {"name": name, "value": value, "status": status, "message": message}


def evaluate(crop: str | None, weather: dict) -> dict:
    ranges = CROP_RANGES.get((crop or "").lower())
    known_crop = ranges is not None
    ranges = ranges or DEFAULT_RANGE
    t_lo, t_hi = ranges["temp"]
    r_lo, r_hi = ranges["rain_7d"]

    temp = weather["current"]["temperature_c"]
    rain_7d = weather["rainfall_mm_7d"]
    forecast = weather["forecast"]
    max_temp = max(d["temp_max_c"] for d in forecast)
    rain_next = round(sum(d["rain_mm"] or 0 for d in forecast), 1)

    factors = []

    # 1. Current temperature
    if t_lo <= temp <= t_hi:
        factors.append(make_factor("temperature_c", temp, "good",
                                   "Temperature is within the ideal range."))
    else:
        factors.append(make_factor("temperature_c", temp, "warning",
                                   f"Temperature is outside the ideal range ({t_lo}-{t_hi} °C)."))

    # 2. Rain in the last 7 days
    if rain_7d < r_lo / 2:
        factors.append(make_factor("rainfall_mm_7d", rain_7d, "risk",
                                   "Very little rain in the last 7 days: drought risk."))
    elif rain_7d < r_lo:
        factors.append(make_factor("rainfall_mm_7d", rain_7d, "warning",
                                   "Rain in the last 7 days is below what the crop needs."))
    elif rain_7d > r_hi:
        factors.append(make_factor("rainfall_mm_7d", rain_7d, "warning",
                                   "Too much rain: check drainage and watch for fungal disease."))
    else:
        factors.append(make_factor("rainfall_mm_7d", rain_7d, "good",
                                   "Rain in the last 7 days is adequate."))

    # 3. Heat in the next days
    if max_temp > t_hi:
        factors.append(make_factor("forecast_max_temp_c", max_temp, "warning",
                                   "Heat expected in the next days: crop may be stressed."))
    else:
        factors.append(make_factor("forecast_max_temp_c", max_temp, "good",
                                   "No heat stress expected in the next days."))

    # 4. Rain in the next days
    if rain_7d < r_lo and rain_next < 5:
        factors.append(make_factor("forecast_rain_mm", rain_next, "warning",
                                   "Dry week and little rain forecast: consider irrigation."))
    else:
        factors.append(make_factor("forecast_rain_mm", rain_next, "good",
                                   "Forecast rain is not a concern."))

    statuses = {f["status"] for f in factors}
    if "risk" in statuses:
        status = "risk"
    elif "warning" in statuses:
        status = "attention"
    else:
        status = "favorable"

    recommendations = [f["message"] for f in factors if f["status"] != "good"]
    if not recommendations:
        recommendations = ["Conditions look favorable. Keep monitoring."]

    limitations = ["Uses weather data only (no soil data yet)."]
    if not known_crop:
        limitations.append("Crop not recognized: generic ranges were used.")

    return {
        "status": status,
        "confidence": "medium" if known_crop else "low",
        "factors": factors,
        "recommendations": recommendations,
        "limitations": limitations,
    }


@router.get("/{farm_id}/analysis")
def farm_analysis(farm_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    farm = get_farm_with_coords(db, farm_id)
    weather = fetch_weather(farm["latitude"], farm["longitude"])
    return {
        "farm": {"id": farm["id"], "name": farm["name"], "crop": farm["crop"]},
        "disclaimer": DISCLAIMER,
        **evaluate(farm["crop"], weather),
    }
