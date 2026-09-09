"""Auth package — JWT login/refresh/logout + bcrypt password hashing.

Feature routes stay public by design; auth protects only routes that opt in
via `Depends(get_current_user)`. Refresh-token revocation uses Redis when
available and degrades to stateless refresh when it isn't.
"""
