"""OAuth routes for connecting a user's Google account to Gmail."""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config.settings import get_settings
from app.models.oauth_state import OAuthState
from app.models.user import User
from app.repositories import credential_repo
from app.services.credential_service import encrypt_data

router = APIRouter(prefix="/integrations/google", tags=["integrations"])
logger = logging.getLogger(__name__)
_SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().SECRET_KEY, salt="gmail-oauth-state")


def _create_authorization_url(current_user: User, db: Session) -> str:
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    nonce = str(uuid.uuid4())
    db.query(OAuthState).filter(
        OAuthState.expires_at <= datetime.now(UTC)
    ).delete(synchronize_session=False)
    db.add(OAuthState(user_id=current_user.id, nonce=nonce, expires_at=datetime.now(UTC) + timedelta(minutes=10)))
    db.commit()
    state = _serializer().dumps({"user_id": str(current_user.id), "nonce": nonce})
    query = urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": _SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


@router.get("/auth")
def google_auth(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> RedirectResponse:
    return RedirectResponse(_create_authorization_url(current_user, db), status_code=302)


@router.get("/auth-url")
def google_auth_url(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, str]:
    """Return a signed, one-time authorization URL for authenticated popup clients."""
    return {"authorization_url": _create_authorization_url(current_user, db)}


def _popup_result(status_value: str) -> HTMLResponse:
    frontend_url = get_settings().FRONTEND_URL
    parsed = urlsplit(frontend_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=500, detail="FRONTEND_URL must be an absolute HTTP(S) URL")
    target_origin = f"{parsed.scheme}://{parsed.netloc}"
    message_json = json.dumps(
        {"type": "flowforge:google-oauth", "status": status_value}
    ).replace("<", "\\u003c")
    target_json = json.dumps(target_origin).replace("<", "\\u003c")
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>FlowForge Google OAuth</title>"
        "<p>Google connection finished. You can close this window.</p>"
        f"<script>if(window.opener){{window.opener.postMessage({message_json},{target_json});window.close();}}</script>"
    )


@router.get("/callback")
def google_callback(
    code: str | None = Query(None, min_length=1),
    state: str = Query(..., min_length=1),
    error: str | None = Query(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
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
        OAuthState.expires_at > datetime.now(UTC),
    ).with_for_update().first()
    if state_row is None:
        raise HTTPException(status_code=400, detail="OAuth state has already been used or expired")
    db.delete(state_row)
    db.commit()

    if error:
        return _popup_result("denied")
    if not code:
        raise HTTPException(status_code=400, detail="Google OAuth code is missing")

    from app.integrations.gmail import exchange_code

    try:
        tokens = exchange_code(code, settings)
    except Exception as exc:
        logger.warning("Google OAuth callback could not exchange authorization code (%s)", type(exc).__name__)
        return _popup_result("error")
    if not tokens.get("refresh_token"):
        logger.warning("Google OAuth callback returned no refresh token; credential was not saved")
        return _popup_result("error")
    tokens["expiry"] = (datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat()
    try:
        credential_repo.create(
            db,
            user_id=user_id,
            name="Google Gmail",
            type="oauth2_google",
            encrypted_data=encrypt_data(tokens),
        )
    except Exception as exc:
        db.rollback()
        logger.warning("Google OAuth credential could not be persisted (%s)", type(exc).__name__)
        return _popup_result("error")
    return _popup_result("connected")
