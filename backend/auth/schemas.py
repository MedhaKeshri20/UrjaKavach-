"""Auth request/response models (API surface, not the frozen risk-state contract)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# The role a user selects at registration. The frontend renders this as a
# dropdown; picking one decides which dashboard they land on after signup.
# Mirrors the frontend `type UserRole = "citizen" | "official"`.
Role = Literal["citizen", "official"]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=6, description="Plaintext; hashed server-side.")
    role: Role = Field(default="citizen", description="'citizen' or 'official'.")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Returned by both register and login so the portal can route straight to
    the matching dashboard using ``role``."""

    access_token: str
    token_type: str = "bearer"
    role: Role
    email: EmailStr
    # Where the frontend should send this user next. Convenience only — the
    # portal may ignore it and route on ``role`` itself.
    dashboard: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: Role
