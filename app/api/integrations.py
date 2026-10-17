"""OAuth routes for connecting a user's Google account to Gmail."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config.settings import get_settings
from app.models.user import User
from app.models.oauth_state import OAuthState
from app.repositories import credential_repo
from app.services.credential_service import encrypt_data

router = APIRouter(prefix="/integrations/google", tags=["integrations"])
_SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().SECRET_KEY, salt="gmail-oauth-state")


@router.get("/auth")
def google_auth(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> RedirectResponse:
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    nonce = str(uuid.uuid4())
    db.query(OAuthState).filter(
        OAuthState.expires_at <= datetime.now(timezone.utc)
    ).delete(synchronize_session=False)
    db.add(OAuthState(user_id=current_user.id, nonce=nonce, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)))
    db.commit()
    state = _serializer().dumps({"user_id": str(current_user.id), "nonce": nonce})
    from urllib.parse import urlencode

    query = urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}", status_code=302)


@router.get("/callback")
def google_callback(
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    try:
        payload = _serializer().loads(state, max_age=600)
        user_id = uuid.UUID(payload["user_id"])
        nonce = payload["nonce"]
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state") from exc
    from app.repositories import user_repo

    user = user_repo.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="OAuth account owner is unavailable")
    state_row = db.query(OAuthState).filter(
        OAuthState.nonce == nonce, OAuthState.user_id == user_id,
        OAuthState.expires_at > datetime.now(timezone.utc),
    ).with_for_update().first()
    if state_row is None:
        raise HTTPException(status_code=400, detail="OAuth state has already been used or expired")
    db.delete(state_row)
    db.commit()
    from app.integrations.gmail import exchange_code

    try:
        tokens = exchange_code(code, settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Google OAuth exchange failed") from exc
    if not tokens.get("refresh_token"):
        raise HTTPException(status_code=502, detail="Google did not return a refresh token")
    tokens["expiry"] = (datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat()
    credential_repo.create(
        db,
        user_id=user_id,
        name="Google Gmail",
        type="oauth2_google",
        encrypted_data=encrypt_data(tokens),
    )
    return {"connected": True}
