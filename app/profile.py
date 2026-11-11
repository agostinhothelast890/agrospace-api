from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user
from app.farms import get_db

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileUpdate(BaseModel):
    full_name: str


@router.get("")
def get_profile(user=Depends(get_current_user), db=Depends(get_db)):
    result = db.table("profiles").select("*").eq("id", user.id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {**result.data[0], "email": user.email}


@router.put("")
def update_profile(
    data: ProfileUpdate, user=Depends(get_current_user), db=Depends(get_db)
):
    result = (
        db.table("profiles")
        .update({"full_name": data.full_name})
        .eq("id", user.id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {**result.data[0], "email": user.email}
