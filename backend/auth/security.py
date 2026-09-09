"""
Password hashing (bcrypt) + JWT encode/decode/issuance.

Uses `bcrypt` and `PyJWT` directly rather than passlib: fewer moving parts and
no passlib↔bcrypt version friction on a fresh install. Passwords are pre-hashed
with SHA-256 → base64 before bcrypt so inputs longer than bcrypt's 72-byte limit
aren't silently truncated.
"""

import base64
import hashlib
import time
import uuid
from typing import Optional

import bcrypt
import jwt
from loguru import logger

from backend.config import settings

# Dev-only fallback so local runs work without a configured secret. A warning
# fires once on first use; a real deploy MUST set JWT_SECRET.
_DEV_SECRET = "dev-insecure-secret-change-me"
_warned = False


def _secret() -> str:
    global _warned
    s = (settings.jwt_secret or "").strip()
    if s:
        return s
    if not _warned:
        logger.warning(
            "JWT_SECRET is unset — using an insecure dev secret. "
            "Set JWT_SECRET in the environment before deploying."
        )
        _warned = True
    return _DEV_SECRET


# -- password hashing --------------------------------------------------------

def _prehash(password: str) -> bytes:
    """SHA-256 → base64 so any-length password fits bcrypt's 72-byte input."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("utf-8"))
    except Exception:
        return False


# -- JWT ---------------------------------------------------------------------

def _encode(claims: dict) -> str:
    return jwt.encode(claims, _secret(), algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, email: str) -> str:
    now = int(time.time())
    return _encode({
        "sub": user_id,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + settings.access_token_expire_minutes * 60,
    })


def create_refresh_token(user_id: str) -> tuple[str, str, int]:
    """Return (token, jti, ttl_seconds). The jti is stored in Redis for revocation."""
    now = int(time.time())
    jti = uuid.uuid4().hex
    ttl = settings.refresh_token_expire_days * 86400
    token = _encode({
        "sub": user_id,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
    })
    return token, jti, ttl


def decode_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
    """Decode + verify signature/expiry. Returns claims, or None if invalid or
    the wrong token type."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if expected_type and claims.get("type") != expected_type:
        return None
    return claims
