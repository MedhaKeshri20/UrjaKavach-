"""JWT auth guards used as FastAPI dependencies.

``get_current_user`` verifies the Bearer token and loads the user; ``require_role``
builds a dependency that additionally enforces a role, so an official-only route
is simply ``Depends(require_role("official"))``.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.auth.models import User
from backend.auth.security import decode_token
from backend.db import get_session

# auto_error=False so we can raise our own 401 with a clean message.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the authenticated user from the Bearer token, or raise 401."""

    if credentials is None or not credentials.credentials:
        raise _UNAUTHENTICATED
    try:
        claims = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    except jwt.PyJWTError:
        raise _UNAUTHENTICATED

    email = claims.get("sub")
    user = (
        session.query(User).filter(User.email == email).one_or_none()
        if email
        else None
    )
    if user is None:
        raise _UNAUTHENTICATED
    return user


def require_role(role: str):
    """Dependency factory: allow only users holding ``role`` (else 403)."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{role}' role",
            )
        return user

    return _guard
