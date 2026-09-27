"""Auth endpoints: register, login, and 'who am I'.

Register accepts a role ('public' or 'official') and logs the user straight in
(returns a token), so the frontend can route to the matching dashboard on
signup without a second round-trip.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.auth.models import User
from backend.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from backend.auth.security import create_access_token, hash_password, verify_password
from backend.db import get_session
from backend.middleware.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

# Where each role lands after auth. The frontend owns the actual routes; this is
# a convenience hint returned alongside the token.
_DASHBOARD = {"official": "/official", "citizen": "/citizen"}


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(subject=user.email, role=user.role)
    return TokenResponse(
        access_token=token,
        role=user.role,
        email=user.email,
        dashboard=_DASHBOARD.get(user.role, "/citizen"),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Create an account with the chosen role and return an access token."""

    exists = session.query(User).filter(User.email == body.email).one_or_none()
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    """Verify credentials and return an access token + landing dashboard."""

    user = session.query(User).filter(User.email == body.email).one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    """Return the currently authenticated user."""

    return UserOut(id=user.id, email=user.email, role=user.role)
