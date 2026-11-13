from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.dashboard import router as dashboard_router
from app.farms import router as farms_router
from app.profile import router as profile_router
from app.weather import router as weather_router
from app.analysis import router as analysis_router
from app.soil import router as soil_router
from app.ai import router as ai_router
from app.nasa import router as nasa_router
from app.errors import register_error_handlers

app = FastAPI(title="AgroSpace API", version="0.1.0")
register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(farms_router)
app.include_router(dashboard_router)
app.include_router(weather_router)
app.include_router(analysis_router)
app.include_router(soil_router)
app.include_router(ai_router)
app.include_router(nasa_router)


@app.get("/")
def root():
    return {"name": "AgroSpace API", "version": "0.1.0"}


@app.get("/api/health")
def health():
    return {"status": "ok"}
