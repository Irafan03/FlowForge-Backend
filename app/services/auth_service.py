"""
Authentication service: password hashing (bcrypt) and JWT creation/validation.
No secrets are ever logged or returned in error messages.
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config.settings import get_settings

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password helpers ───────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── JWT helpers ────────────────────────────────────────────────────────────────

def create_access_token(user_id: str) -> tuple[str, int]:
    """
    Returns (token, expires_in_seconds).
    Payload: { sub: user_id, exp: ... }
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def decode_access_token(token: str) -> str:
    """
    Decodes a JWT and returns the user_id (sub claim).
    Raises ValueError on invalid/expired token — never leaks key material.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise ValueError("Token missing sub claim")
        return user_id
    except JWTError as exc:
        # Do NOT include `exc` details in the message — it may contain key info
        raise ValueError("Invalid or expired token") from exc
