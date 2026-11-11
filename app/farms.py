from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.auth import bearer, get_current_user
from app.supabase_client import get_user_client

router = APIRouter(prefix="/api/farms", tags=["farms"])


class FarmIn(BaseModel):
    name: str
    crop: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    area_ha: float | None = None


class FarmUpdate(BaseModel):
    name: str | None = None
    crop: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    area_ha: float | None = None


def get_db(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    return get_user_client(credentials.credentials)


@router.post("")
def create_farm(data: FarmIn, user=Depends(get_current_user), db=Depends(get_db)):
    row = {**data.model_dump(), "owner_id": user.id}
    result = db.table("farms").insert(row).execute()
    return result.data[0]


@router.get("")
def list_farms(user=Depends(get_current_user), db=Depends(get_db)):
    result = db.table("farms").select("*").order("created_at", desc=True).execute()
    return result.data


@router.get("/{farm_id}")
def get_farm(farm_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    result = db.table("farms").select("*").eq("id", str(farm_id)).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Farm not found")
    return result.data[0]


@router.put("/{farm_id}")
def update_farm(
    farm_id: UUID,
    data: FarmUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = db.table("farms").update(changes).eq("id", str(farm_id)).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Farm not found")
    return result.data[0]


@router.delete("/{farm_id}")
def delete_farm(farm_id: UUID, user=Depends(get_current_user), db=Depends(get_db)):
    result = db.table("farms").delete().eq("id", str(farm_id)).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Farm not found")
    return {"deleted": True}
