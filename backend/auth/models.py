"""User table for authentication.

Registers on the shared declarative ``Base`` so ``init_db`` creates it alongside
the other tables. Passwords are never stored in the clear — only a bcrypt hash.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base
from backend.models import utcnow

# The two roles the system understands. A registering user picks one (the
# frontend renders this as a dropdown); the API validates against this set.
# Matches the frontend `type UserRole = "citizen" | "official"`.
ROLES = ("citizen", "official")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="citizen")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
