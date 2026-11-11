from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.supabase_client import get_client

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer()


class SignupIn(BaseModel):
    email: str
    password: str
    full_name: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
):
    """Checks the token with Supabase and returns the user, or 401."""
    try:
        result = get_client().auth.get_user(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not result or not result.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return result.user


@router.post("/signup")
def signup(data: SignupIn):
    try:
        result = get_client().auth.sign_up(
            {
                "email": data.email,
                "password": data.password,
                "options": {"data": {"full_name": data.full_name}},
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result.user:
        raise HTTPException(status_code=400, detail="Could not create account")
    return {"id": result.user.id, "email": result.user.email}


@router.post("/login")
def login(data: LoginIn):
    try:
        result = get_client().auth.sign_in_with_password(
            {"email": data.email, "password": data.password}
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "access_token": result.session.access_token,
        "token_type": "bearer",
    }


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"id": user.id, "email": user.email}
