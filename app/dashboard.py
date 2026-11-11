from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.farms import get_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(user=Depends(get_current_user), db=Depends(get_db)):
    profile = db.table("profiles").select("full_name").eq("id", user.id).execute().data
    farms = db.table("farms").select("*").order("created_at", desc=True).execute().data

    # Count farms per crop, e.g. {"maize": 2, "unknown": 1}
    crops: dict[str, int] = {}
    for farm in farms:
        crop = farm.get("crop") or "unknown"
        crops[crop] = crops.get(crop, 0) + 1

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": profile[0]["full_name"] if profile else None,
        },
        "farm_count": len(farms),
        "total_area_ha": sum(float(f["area_ha"] or 0) for f in farms),
        "crops": crops,
        "farms": farms,
    }
