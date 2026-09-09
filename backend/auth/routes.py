"""
Auth routes — register / login / refresh / logout / me.

Users live in the `users` collection of the existing structured_store (Mongo or
JSON fallback). That store has no unique index, so register does an app-level
duplicate-email check. Refresh tokens are tracked in Redis by their `jti` so
logout can revoke them; without Redis, refresh still works (signature + expiry)
but can't be server-side revoked — logout then only clears the client's copy.
"""

import re
import time

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from backend.auth.deps import get_current_user
from backend.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from backend.cache import cache
from backend.db.mongo_store import structured_store

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# -- schemas -----------------------------------------------------------------

# Lightweight email check — avoids the email-validator dependency that
# pydantic's EmailStr pulls in. Good enough for a login form; the auth flow
# doesn't rely on deliverability.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(v: str) -> str:
    v = (v or "").strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("Invalid email address")
    return v


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=120)

    _v_email = field_validator("email")(classmethod(lambda cls, v: _validate_email(v)))


class LoginRequest(BaseModel):
    email: str
    password: str

    _v_email = field_validator("email")(classmethod(lambda cls, v: _validate_email(v)))


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


# -- helpers -----------------------------------------------------------------

def _issue_tokens(user: dict) -> TokenResponse:
    access = create_access_token(user["_id"], user["email"])
    refresh, jti, ttl = create_refresh_token(user["_id"])
    cache.store_refresh_token(jti, user["_id"], ttl)
    public = {k: v for k, v in user.items() if k != "password_hash"}
    return TokenResponse(access_token=access, refresh_token=refresh, user=public)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


# -- routes ------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    email = _normalize_email(req.email)
    if structured_store.find_one("users", {"email": email}):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = {
        "email": email,
        "name": req.name.strip(),
        "password_hash": hash_password(req.password),
        "created_at": int(time.time()),
    }
    user_id = structured_store.insert("users", user)
    user["_id"] = user_id
    logger.info(f"Registered user: {email}")
    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    email = _normalize_email(req.email)
    user = structured_store.find_one("users", {"email": email})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest):
    claims = decode_token(req.refresh_token, expected_type="refresh")
    if not claims:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    jti = claims.get("jti")
    # When Redis is enabled, the jti MUST still be present (revoked → absent).
    # When Redis is disabled, store_refresh_token was a no-op, so we can't check
    # revocation — accept on signature+expiry alone (documented degradation).
    if cache.enabled:
        if not jti or cache.refresh_token_user(jti) != claims.get("sub"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired")
        cache.revoke_refresh_token(jti)  # rotate: old refresh is single-use

    user = structured_store.find_one("users", {"_id": claims.get("sub")})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return _issue_tokens(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(req: RefreshRequest):
    """Revoke the given refresh token. Idempotent — unknown/expired tokens 204."""
    claims = decode_token(req.refresh_token, expected_type="refresh")
    if claims and claims.get("jti"):
        cache.revoke_refresh_token(claims["jti"])
    return None


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Protected sample route — proves Bearer validation works end to end."""
    return user
