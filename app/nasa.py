from datetime import date, timedelta
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.farms import get_db
from app.weather import get_farm_with_coords

router = APIRouter(prefix="/api/farms", tags=["nasa"])

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
FILL_VALUE = -999  # POWER uses -999 for days without data yet

# One call per location per day is enough (the data is daily).
_cache: dict[tuple[float, float, str], dict] = {}
_last_error = {"message": ""}


def fetch_nasa(latitude: float, longitude: float) -> dict | None:
    """Returns NASA POWER daily data summary, or None if unavailable."""
    today = date.today()
    key = (round(latitude, 2), round(longitude, 2), today.isoformat())
    if key in _cache:
        return _cache[key]

    params = {
        "parameters": "T2M,PRECTOTCORR,RH2M,GWETROOT",
        "community": "AG",
        "latitude": latitude,
        "longitude": longitude,
        "start": (today - timedelta(days=14)).strftime("%Y%m%d"),
        "end": (today - timedelta(days=1)).strftime("%Y%m%d"),
        "format": "JSON",
    }
    try:
        response = httpx.get(POWER_URL, params=params, timeout=30)
        response.raise_for_status()
        series = response.json()["properties"]["parameter"]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        _last_error["message"] = repr(e)[:200]
        print(f"NASA POWER error: {e!r}")
        return None

    def valid(name: str) -> dict[str, float]:
        values = series.get(name, {})
        return {d: v for d, v in values.items() if v is not None and v != FILL_VALUE}

    temp, rain = valid("T2M"), valid("PRECTOTCORR")
    hum, wet = valid("RH2M"), valid("GWETROOT")
    if not (temp or rain or wet):
        _last_error["message"] = f"no valid values, keys: {list(series.keys())}"
        print(f"NASA POWER: {_last_error['message']}")
        return None

    def latest(values: dict[str, float]):
        return values[max(values)] if values else None

    latest_day = max(temp or rain or wet)
    last_7_rain_days = sorted(rain)[-7:]

    nasa = {
        "source": "NASA POWER",
        "latest_date": f"{latest_day[:4]}-{latest_day[4:6]}-{latest_day[6:]}",
        "temperature_c": latest(temp),
        "humidity_pct": latest(hum),
        "rainfall_mm_7d": round(sum(rain[d] for d in last_7_rain_days), 1) if rain else None,
        # 0 = very dry, 1 = saturated
        "root_zone_wetness": latest(wet),
    }
    _cache[key] = nasa
    return nasa


def nasa_wetness_factor(nasa: dict | None) -> dict | None:
    """Analysis factor from NASA root-zone soil wetness (demo thresholds)."""
    wet = nasa.get("root_zone_wetness") if nasa else None
    if wet is None:
        return None
    if wet < 0.25:
        status, message = "risk", "NASA data shows very dry soil in the root zone."
    elif wet < 0.4:
        status, message = "warning", "NASA data shows low soil moisture in the root zone."
    elif wet > 0.85:
        status, message = "warning", "NASA data shows very wet soil: watch drainage."
    else:
        status, message = "good", "NASA data shows adequate soil moisture in the root zone."
    return {"name": "soil_wetness_nasa", "value": wet, "status": status, "message": message}


@router.get("/{farm_id}/nasa")
def farm_nasa(farm_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    farm = get_farm_with_coords(db, farm_id)
    nasa = fetch_nasa(farm["latitude"], farm["longitude"])
    if nasa is None:
        raise HTTPException(
            status_code=503,
            detail=f"NASA POWER unavailable: {_last_error['message']}",
        )
    return {"farm": {"id": farm["id"], "name": farm["name"]}, **nasa}
