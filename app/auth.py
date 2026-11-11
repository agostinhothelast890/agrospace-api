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


class RefreshIn(BaseModel):
    refresh_token: str


def token_response(session) -> dict:
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_in": session.expires_in,
        "token_type": "bearer",
    }


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
    return token_response(result.session)


@router.post("/refresh")
def refresh(data: RefreshIn):
    try:
        result = get_client().auth.refresh_session(data.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if not result or not result.session:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return token_response(result.session)


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"id": user.id, "email": user.email}
