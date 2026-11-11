from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.farms import get_db
from app.weather import get_farm_with_coords

router = APIRouter(prefix="/api/farms", tags=["soil"])

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Soil does not change fast, and SoilGrids limits calls (about 5 per minute),
# so we remember results per location.
_cache: dict[tuple[float, float], dict] = {}


def fetch_soil(latitude: float, longitude: float) -> dict | None:
    """Returns soil values for the top 5 cm, or None if unavailable."""
    key = (round(latitude, 3), round(longitude, 3))
    if key in _cache:
        return _cache[key]

    params = [
        ("lat", latitude),
        ("lon", longitude),
        ("depth", "0-5cm"),
        ("value", "mean"),
        ("property", "phh2o"),
        ("property", "soc"),
        ("property", "clay"),
        ("property", "sand"),
    ]
    try:
        response = httpx.get(SOILGRIDS_URL, params=params, timeout=25)
        response.raise_for_status()
        layers = response.json()["properties"]["layers"]
    except (httpx.HTTPError, KeyError, ValueError):
        return None

    values: dict[str, float | None] = {}
    for layer in layers:
        factor = layer["unit_measure"].get("d_factor") or 1
        mean = layer["depths"][0]["values"].get("mean")
        values[layer["name"]] = None if mean is None else round(mean / factor, 1)

    if all(v is None for v in values.values()):
        return None

    soil = {
        "source": "SoilGrids (ISRIC)",
        "depth": "0-5 cm",
        "ph": values.get("phh2o"),
        "organic_carbon_g_kg": values.get("soc"),
        "clay_pct": values.get("clay"),
        "sand_pct": values.get("sand"),
    }
    _cache[key] = soil
    return soil


@router.get("/{farm_id}/soil")
def farm_soil(farm_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    farm = get_farm_with_coords(db, farm_id)
    soil = fetch_soil(farm["latitude"], farm["longitude"])
    if soil is None:
        raise HTTPException(status_code=503, detail="Soil service unavailable")
    return {"farm": {"id": farm["id"], "name": farm["name"]}, **soil}
