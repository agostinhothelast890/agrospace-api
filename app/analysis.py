from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.farms import get_db
from app.nasa import fetch_nasa, nasa_wetness_factor
from app.soil import fetch_soil
from app.weather import fetch_weather, get_farm_with_coords

router = APIRouter(prefix="/api/farms", tags=["analysis"])

DISCLAIMER = (
    "Demonstration rules based on weather, soil and NASA data. "
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

# Demo ideal soil pH per crop.
PH_RANGES = {
    "maize": (5.8, 7.0),
    "cassava": (5.5, 7.0),
    "beans": (6.0, 7.0),
    "tomato": (6.0, 6.8),
}
DEFAULT_PH = (5.5, 7.5)


def make_factor(name: str, value, status: str, message: str) -> dict:
    return {"name": name, "value": value, "status": status, "message": message}


def weather_from_nasa(nasa: dict | None) -> dict | None:
    """Basic weather built from NASA POWER (backup if Open-Meteo is down)."""
    if not nasa:
        return None
    temp = nasa.get("temperature_c")
    rain = nasa.get("rainfall_mm_7d")
    if temp is None or rain is None:
        return None
    return {
        "source": "NASA POWER",
        "current": {
            "temperature_c": temp,
            "humidity_pct": nasa.get("humidity_pct"),
            "rain_mm": None,
        },
        "rainfall_mm_7d": rain,
        "forecast": [],  # NASA POWER has no forecast
    }


def load_inputs(farm: dict) -> dict:
    """Collects all data sources; uses NASA as weather backup if Open-Meteo fails."""
    lat, lon = farm["latitude"], farm["longitude"]
    nasa = fetch_nasa(lat, lon)
    soil = fetch_soil(lat, lon)
    try:
        weather = fetch_weather(lat, lon)
    except HTTPException:
        weather = weather_from_nasa(nasa)
        if weather is None:
            raise HTTPException(
                status_code=502,
                detail="Weather data unavailable (Open-Meteo and NASA POWER failed)",
            )
    return {"weather": weather, "soil": soil, "nasa": nasa}


def evaluate(
    crop: str | None,
    weather: dict,
    soil: dict | None,
    nasa: dict | None = None,
) -> dict:
    crop_key = (crop or "").lower()
    ranges = CROP_RANGES.get(crop_key)
    known_crop = ranges is not None
    ranges = ranges or DEFAULT_RANGE
    t_lo, t_hi = ranges["temp"]
    r_lo, r_hi = ranges["rain_7d"]

    temp = weather["current"]["temperature_c"]
    rain_7d = weather["rainfall_mm_7d"]
    forecast = weather["forecast"]

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

    # 3 and 4. Forecast factors (skipped when there is no forecast)
    if forecast:
        max_temp = max(d["temp_max_c"] for d in forecast)
        rain_next = round(sum(d["rain_mm"] or 0 for d in forecast), 1)

        if max_temp > t_hi:
            factors.append(make_factor("forecast_max_temp_c", max_temp, "warning",
                                       "Heat expected in the next days: crop may be stressed."))
        else:
            factors.append(make_factor("forecast_max_temp_c", max_temp, "good",
                                       "No heat stress expected in the next days."))

        if rain_7d < r_lo and rain_next < 5:
            factors.append(make_factor("forecast_rain_mm", rain_next, "warning",
                                       "Dry week and little rain forecast: consider irrigation."))
        else:
            factors.append(make_factor("forecast_rain_mm", rain_next, "good",
                                       "Forecast rain is not a concern."))

    # 5. Soil pH (only if soil data is available)
    ph = soil["ph"] if soil else None
    if ph is not None:
        p_lo, p_hi = PH_RANGES.get(crop_key, DEFAULT_PH)
        if ph < p_lo:
            factors.append(make_factor("soil_ph", ph, "warning",
                                       f"Soil is acidic (ideal {p_lo}-{p_hi}): liming may help."))
        elif ph > p_hi:
            factors.append(make_factor("soil_ph", ph, "warning",
                                       f"Soil is alkaline (ideal {p_lo}-{p_hi}): nutrients may be harder to absorb."))
        else:
            factors.append(make_factor("soil_ph", ph, "good",
                                       "Soil pH is within the ideal range."))

    # 6. NASA root-zone soil wetness (only if NASA data is available)
    wetness = nasa_wetness_factor(nasa)
    if wetness:
        factors.append(wetness)

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

    limitations = []
    if weather.get("source") != "Open-Meteo":
        limitations.append(
            "Open-Meteo unavailable: weather comes from NASA POWER "
            "(a few days old, no forecast)."
        )
    if soil:
        limitations.append("Soil values are global estimates (~250 m), not a lab test.")
    else:
        limitations.append("Soil data unavailable right now.")
    if nasa:
        limitations.append("NASA POWER data has ~50 km resolution and a delay of a few days.")
    else:
        limitations.append("NASA data unavailable right now.")
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
    data = load_inputs(farm)
    weather, soil, nasa = data["weather"], data["soil"], data["nasa"]

    data_sources = [weather["source"]]
    if soil:
        data_sources.append("SoilGrids (ISRIC)")
    if nasa and "NASA POWER" not in data_sources:
        data_sources.append("NASA POWER")

    return {
        "farm": {"id": farm["id"], "name": farm["name"], "crop": farm["crop"]},
        "disclaimer": DISCLAIMER,
        "data_sources": data_sources,
        "soil": soil,
        "nasa": nasa,
        **evaluate(farm["crop"], weather, soil, nasa),
    }
