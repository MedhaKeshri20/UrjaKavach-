"""Password hashing (bcrypt) and JWT encode/decode.

Kept free of FastAPI/DB imports so it stays a pure, unit-testable crypto helper.
Secret + algorithm + expiry come from :class:`Settings` (env-driven).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from backend.config import Settings, get_settings


# bcrypt only considers the first 72 bytes of a password and (in 4.x+) raises on
# anything longer. We truncate to 72 bytes in BOTH hash and verify so they stay
# consistent and a long password never 500s the register/login endpoints.
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a bcrypt hash of ``password`` (utf-8 string, safe to store)."""

    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time check of a plaintext password against a stored hash."""

    try:
        return bcrypt.checkpw(_prepare(password), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash in the DB -> treat as a failed login, never crash.
        return False


def create_access_token(
    subject: str, role: str, settings: Settings | None = None
) -> str:
    """Issue a signed JWT carrying the user's email (``sub``) and ``role``."""

    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expiry_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: Settings | None = None) -> dict:
    """Verify signature + expiry and return the claims. Raises on failure."""

    settings = settings or get_settings()
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
