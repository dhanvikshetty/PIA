"""
FastAPI dependencies for auth.

`get_current_user` validates an `Authorization: Bearer <access-token>` header and
returns the user record (minus the password hash). Attach it to any route that
should require login: `user = Depends(get_current_user)`. Existing feature
routes deliberately do NOT use it — they stay public.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth.security import decode_token
from backend.db.mongo_store import structured_store

# auto_error=False so we can raise a consistent 401 with a WWW-Authenticate header.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _public_user(user: dict) -> dict:
    """Strip sensitive fields before returning a user to a caller."""
    return {k: v for k, v in user.items() if k != "password_hash"}


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    if creds is None or not creds.credentials:
        raise _UNAUTHORIZED
    claims = decode_token(creds.credentials, expected_type="access")
    if not claims:
        raise _UNAUTHORIZED
    user = structured_store.find_one("users", {"_id": claims.get("sub")})
    if not user:
        raise _UNAUTHORIZED
    return _public_user(user)
