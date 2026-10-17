"""
FastAPI dependency providers:
- get_db()            → SQLAlchemy session (per-request, auto-closed)
- get_current_user()  → authenticated User from Bearer JWT
"""

from __future__ import annotations

from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings

# ── Database ───────────────────────────────────────────────────────────────────

_settings = get_settings()
_engine = create_engine(
    _settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
_SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a DB session and ensure it's closed after the request."""
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Authentication ─────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
):
    """
    Decode the JWT Bearer token and return the matching User.
    Raises 401 on invalid/expired token, 404 if the user no longer exists.
    """
    from app.models.user import User
    from app.repositories import user_repo
    from app.services.auth_service import decode_access_token

    token = credentials.credentials
    try:
        user_id_str = decode_access_token(token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    import uuid
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = user_repo.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
