"""AgroSpace OFFLINE demo server.

Same routes and JSON as the real API, but everything lives in memory and the
data is a saved sample. For demos only: it is NOT secure and forgets everything
when it stops.
"""
import os
import secrets
import uuid
from datetime import datetime, timezone
from uuid import UUID

# The real modules read these at import time; offline they are never used.
os.environ.setdefault("SUPABASE_URL", "http://offline.local")
os.environ.setdefault("SUPABASE_KEY", "offline")

from fastapi import Depends, FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402

from app.ai import AIRequest, ChatRequest  # noqa: E402
from app.analysis import DISCLAIMER, evaluate  # noqa: E402
from app.auth import LoginIn, RefreshIn, SignupIn  # noqa: E402
from app.errors import register_error_handlers  # noqa: E402
from app.farms import FarmIn, FarmUpdate  # noqa: E402
from app.profile import ProfileUpdate  # noqa: E402

app = FastAPI(title="AgroSpace API (OFFLINE DEMO)", version="0.1.0-offline")
register_error_handlers(app)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ---------- Saved sample data (same for every farm) ----------
# "source" must stay exactly "Open-Meteo" for evaluate(); labels are added below.
SAMPLE_WEATHER = {
    "source": "Open-Meteo",
    "current": {"temperature_c": 25.9, "humidity_pct": 79, "rain_mm": 0},
    "rainfall_mm_7d": 29.5,
    "forecast": [
        {"date": "2026-11-11", "temp_max_c": 29.4, "temp_min_c": 24.8, "rain_mm": 0},
        {"date": "2026-11-12", "temp_max_c": 27.4, "temp_min_c": 24.3, "rain_mm": 3.8},
        {"date": "2026-11-13", "temp_max_c": 28.9, "temp_min_c": 23.6, "rain_mm": 0},
    ],
}
# Illustrative values: replace them with real SoilGrids values if you have them.
SAMPLE_SOIL = {
    "source": "SoilGrids (illustrative sample)",
    "depth": "0-5 cm",
    "ph": 6.1,
    "organic_carbon_g_kg": 18.0,
    "clay_pct": 24.0,
    "sand_pct": 52.0,
}
SAMPLE_NASA = {
    "source": "NASA POWER (saved sample)",
    "latest_date": "2026-11-10",
    "temperature_c": 27.51,
    "humidity_pct": 79,
    "rainfall_mm_7d": 17.9,
    "root_zone_wetness": 0.28,
}
OFFLINE_SOURCES = [
    "Open-Meteo (saved sample)",
    "SoilGrids (illustrative sample)",
    "NASA POWER (saved sample)",
]

# ---------- In-memory "database" ----------
USERS: dict[str, dict] = {}    # email -> user
ACCESS: dict[str, str] = {}    # access token -> user id
REFRESH: dict[str, str] = {}   # refresh token -> user id
FARMS: dict[str, dict] = {}    # farm id -> farm
bearer = HTTPBearer()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_user(email: str, password: str, full_name: str | None) -> dict:
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password": password,
        "full_name": full_name,
        "created_at": now(),
    }
    USERS[email.lower()] = user
    return user


def new_farm(owner_id: str, **fields) -> dict:
    farm = {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "name": fields["name"],
        "crop": fields.get("crop"),
        "latitude": fields.get("latitude"),
        "longitude": fields.get("longitude"),
        "area_ha": fields.get("area_ha"),
        "created_at": now(),
    }
    FARMS[farm["id"]] = farm
    return farm


def issue_tokens(user_id: str) -> dict:
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    ACCESS[access] = user_id
    REFRESH[refresh] = user_id
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": 3600,
        "token_type": "bearer",
    }


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    user_id = ACCESS.get(credentials.credentials)
    user = next((u for u in USERS.values() if u["id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def own_farm(user: dict, farm_id: UUID) -> dict:
    farm = FARMS.get(str(farm_id))
    if not farm or farm["owner_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


def user_farms(user: dict) -> list[dict]:
    farms = [f for f in FARMS.values() if f["owner_id"] == user["id"]]
    return sorted(farms, key=lambda f: f["created_at"], reverse=True)


# Demo account, ready to use: demo@agrospace.com / 123456
_demo = new_user("demo@agrospace.com", "123456", "Demo")
new_farm(_demo["id"], name="Fazenda Demo", crop="maize",
         latitude=-8.84, longitude=13.23, area_ha=220)


# ---------- Basic ----------
@app.get("/")
def root():
    return {"name": "AgroSpace API", "version": "0.1.0-offline", "mode": "offline"}


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "offline"}


# ---------- Auth ----------
@app.post("/api/auth/signup")
def signup(data: SignupIn):
    if data.email.lower() in USERS:
        raise HTTPException(status_code=400, detail="User already registered")
    user = new_user(data.email, data.password, data.full_name)
    return {"id": user["id"], "email": user["email"]}


@app.post("/api/auth/login")
def login(data: LoginIn):
    user = USERS.get(data.email.lower())
    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return issue_tokens(user["id"])


@app.post("/api/auth/refresh")
def refresh(data: RefreshIn):
    user_id = REFRESH.pop(data.refresh_token, None)  # each refresh token works once
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return issue_tokens(user_id)


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return {"id": user["id"], "email": user["email"]}


# ---------- Profile ----------
def profile_view(user: dict) -> dict:
    return {
        "id": user["id"],
        "full_name": user["full_name"],
        "created_at": user["created_at"],
        "email": user["email"],
    }


@app.get("/api/profile")
def get_profile(user=Depends(current_user)):
    return profile_view(user)


@app.put("/api/profile")
def update_profile(data: ProfileUpdate, user=Depends(current_user)):
    user["full_name"] = data.full_name
    return profile_view(user)


# ---------- Farms ----------
@app.post("/api/farms")
def create_farm(data: FarmIn, user=Depends(current_user)):
    return new_farm(user["id"], **data.model_dump())


@app.get("/api/farms")
def list_farms(user=Depends(current_user)):
    return user_farms(user)


@app.get("/api/farms/{farm_id}")
def get_farm(farm_id: UUID, user=Depends(current_user)):
    return own_farm(user, farm_id)


@app.put("/api/farms/{farm_id}")
def update_farm(farm_id: UUID, data: FarmUpdate, user=Depends(current_user)):
    farm = own_farm(user, farm_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")
    farm.update(changes)
    return farm


@app.delete("/api/farms/{farm_id}")
def delete_farm(farm_id: UUID, user=Depends(current_user)):
    farm = own_farm(user, farm_id)
    del FARMS[farm["id"]]
    return {"deleted": True}


# ---------- Dashboard ----------
@app.get("/api/dashboard")
def dashboard(user=Depends(current_user)):
    farms = user_farms(user)
    crops: dict[str, int] = {}
    for farm in farms:
        crop = farm.get("crop") or "unknown"
        crops[crop] = crops.get(crop, 0) + 1
    return {
        "user": {"id": user["id"], "email": user["email"], "full_name": user["full_name"]},
        "farm_count": len(farms),
        "total_area_ha": sum(float(f["area_ha"] or 0) for f in farms),
        "crops": crops,
        "farms": farms,
    }


# ---------- Data (saved samples) ----------
def farm_ref(farm: dict) -> dict:
    return {"id": farm["id"], "name": farm["name"]}


@app.get("/api/farms/{farm_id}/weather")
def farm_weather(farm_id: UUID, user=Depends(current_user)):
    farm = own_farm(user, farm_id)
    return {
        "farm": farm_ref(farm),
        **SAMPLE_WEATHER,
        "source": "Open-Meteo (saved sample)",
        "offline": True,
    }


@app.get("/api/farms/{farm_id}/soil")
def farm_soil(farm_id: UUID, user=Depends(current_user)):
    farm = own_farm(user, farm_id)
    return {"farm": farm_ref(farm), **SAMPLE_SOIL, "offline": True}


@app.get("/api/farms/{farm_id}/nasa")
def farm_nasa(farm_id: UUID, user=Depends(current_user)):
    farm = own_farm(user, farm_id)
    return {"farm": farm_ref(farm), **SAMPLE_NASA, "offline": True}


def run_analysis(farm: dict) -> dict:
    result = evaluate(farm["crop"], SAMPLE_WEATHER, SAMPLE_SOIL, SAMPLE_NASA)
    result["limitations"].insert(0, "OFFLINE DEMO: saved sample data, not live.")
    return result


@app.get("/api/farms/{farm_id}/analysis")
def farm_analysis(farm_id: UUID, user=Depends(current_user)):
    farm = own_farm(user, farm_id)
    return {
        "farm": {"id": farm["id"], "name": farm["name"], "crop": farm["crop"]},
        "disclaimer": DISCLAIMER,
        "offline": True,
        "data_sources": OFFLINE_SOURCES,
        "soil": SAMPLE_SOIL,
        "nasa": SAMPLE_NASA,
        **run_analysis(farm),
    }


# ---------- AI (no internet: simple text instead of Groq) ----------
STATUS_WORDS = {
    "pt": {"favorable": "favorável", "attention": "atenção", "risk": "risco"},
    "en": {"favorable": "favorable", "attention": "attention", "risk": "risk"},
}


@app.post("/api/farms/{farm_id}/explain")
def explain(farm_id: UUID, data: AIRequest, user=Depends(current_user)):
    farm = own_farm(user, farm_id)
    analysis = {"crop": farm["crop"], **run_analysis(farm)}
    lang = "en" if data.lang == "en" else "pt"
    status = STATUS_WORDS[lang][analysis["status"]]
    recommendations = " ".join(analysis["recommendations"])
    if lang == "en":
        text = f"Offline mode (no AI). Farm status: {status}. {recommendations}"
    else:
        text = (
            f"Modo offline (sem IA). Estado da fazenda: {status}. "
            f"Recomendações (em inglês): {recommendations}"
        )
    return {
        "lang": data.lang,
        "ai_available": False,
        "text": text,
        "analysis": analysis,
        "disclaimer": DISCLAIMER,
    }


@app.post("/api/chat")
def chat(data: ChatRequest, user=Depends(current_user)):
    text = (
        "Modo offline: o assistente de IA precisa de internet. "
        "Offline mode: the AI assistant needs an internet connection."
    )
    return {"lang": data.lang, "ai_available": False, "text": text}
