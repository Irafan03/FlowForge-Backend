import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CredentialType = Literal["api_key", "oauth2_google", "telegram_bot", "http_header"]


# ── Request schemas ────────────────────────────────────────────────────────────

class CredentialCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: CredentialType
    # The secret data dict — encrypted before storage, never returned
    data: dict[str, Any]


# ── Response schemas ───────────────────────────────────────────────────────────

class CredentialRead(BaseModel):
    """Public view — never includes the secret data."""
    id: uuid.UUID
    name: str
    type: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
