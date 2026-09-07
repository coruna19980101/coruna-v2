from datetime import timedelta, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db, User, create_audit_log
from ..auth import get_current_user as _auth_get_current_user, invalidate_user_tokens, create_access_token
from ..utils.totp import generate_secret, verify_totp, get_provisioning_uri
from .settings import _set_setting
from ..limiter import rate_limit
from ..config_constants import rate_limit_for

try:
    from .auth import _pending_2fa_setup as _user_setup_tokens
except Exception:
    _user_setup_tokens = {}

router = APIRouter(prefix="/api/auth/2fa", tags=["2fa"], redirect_slashes=False)

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8

_opt_bearer = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def _resolve_user_by_setup_token(request: Request, db: Session):
    raw_token = (
        request.headers.get("X-Setup-Token")
        or request.headers.get("x-setup-token")
        or request.query_params.get("setup_token")
    )
    if not raw_token:
        return None, None, "missing-setup-token"
    now_ts = datetime.now().timestamp()
    key = str(raw_token).strip()
    item = _user_setup_tokens.get(key)
    if not item or item.get("expires_at", 0) < now_ts:
        return None, None, "expired-setup-token"
    username = item.get("username")
    if not username:
        return None, None, "invalid-setup-token"
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None, None, "user-not-found"
    return user, key, None


async def _resolve_effective_user(
    request: Request,
    bearer_token: Optional[str],
    db: Session,
):
    """Resolve user either via Authorization Bearer OR via setup temp token."""
    used_setup = None
    if bearer_token:
        try:
            user = await _auth_get_current_user(token=bearer_token, db=db)
            if user is not None:
                return user, None
        except HTTPException:
            pass
    # Fallback to setup token
    user, setup_tok, err = _resolve_user_by_setup_token(request, db)
    if user is None:
        if bearer_token is None and setup_tok is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        raise HTTPException(status_code=401, detail=f"Invalid credentials: {err or 'unknown'}")
    used_setup = setup_tok
    return user, used_setup


class Enable2FARequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=6)


class Verify2FARequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=6)


@router.get("/setup")
@rate_limit(rate_limit_for("limits.tfa_setup_per_min"))
async def setup_2fa(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    user_obj, used_setup_token = await _resolve_effective_user(request, bearer_token, db)
    if int(getattr(user_obj, "google_2fa_enabled", 0) or 0) == 1:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    secret = generate_secret()
    uri = get_provisioning_uri(secret, user_obj.username)
    user_obj.google_2fa_secret = secret
    user_obj.google_2fa_enabled = 0
    db.commit()
    resp = {"secret": secret, "provisioning_uri": uri, "username": user_obj.username}
    if used_setup_token:
        resp["setup_temp_token"] = used_setup_token
    return resp


@router.post("/enable")
@rate_limit(rate_limit_for("limits.tfa_setup_per_min"))
async def enable_2fa(
    request: Request,
    body: Enable2FARequest,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    user_obj, used_setup_token = await _resolve_effective_user(request, bearer_token, db)
    client_ip = request.client.host if request.client else None
    if int(getattr(user_obj, "google_2fa_enabled", 0) or 0) == 1:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    if not getattr(user_obj, "google_2fa_secret", None):
        raise HTTPException(status_code=400, detail="Please call /setup first to generate a secret")
    if not verify_totp(user_obj.google_2fa_secret, body.token):
        raise HTTPException(status_code=400, detail="Invalid 2FA token")
    user_obj.google_2fa_enabled = 1
    user_obj.failed_2fa_attempts = 0
    user_obj.locked_until = None
    user_obj.last_login = datetime.now()
    if client_ip:
        user_obj.last_login_ip = client_ip
    db.commit()
    create_audit_log(
        db, username=user_obj.username, action="2fa_enabled",
        resource_type="auth", detail="User enabled Google 2FA",
        ip_address=client_ip
    )
    resp = {"message": "2FA enabled successfully"}
    if used_setup_token and used_setup_token in _user_setup_tokens:
        del _user_setup_tokens[used_setup_token]
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user_obj.username, "role": user_obj.role,
                  "ver": getattr(user_obj, "token_version", 0) or 0, "type": "admin"},
            expires_delta=access_token_expires
        )
        resp["access_token"] = access_token
        resp["token_type"] = "bearer"
    return resp


@router.post("/verify")
@rate_limit(rate_limit_for("limits.auth_2fa_per_min"))
async def verify_2fa(
    request: Request,
    body: Verify2FARequest,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    current_user, _ = await _resolve_effective_user(request, bearer_token, db)
    if int(getattr(current_user, "google_2fa_enabled", 0) or 0) != 1 or not getattr(current_user, "google_2fa_secret", None):
        raise HTTPException(status_code=400, detail="2FA not enabled")
    if not verify_totp(current_user.google_2fa_secret, body.token):
        raise HTTPException(status_code=400, detail="Invalid 2FA token")
    return {"valid": True}


@router.post("/disable")
@rate_limit(rate_limit_for("limits.tfa_verify_test_per_min"))
async def disable_2fa(
    request: Request,
    body: Verify2FARequest,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    current_user, used_setup = await _resolve_effective_user(request, bearer_token, db)
    if used_setup:
        raise HTTPException(status_code=403, detail="Must be fully authenticated to disable 2FA")
    if int(getattr(current_user, "google_2fa_enabled", 0) or 0) != 1:
        raise HTTPException(status_code=400, detail="2FA not enabled")
    if not verify_totp(current_user.google_2fa_secret, body.token):
        raise HTTPException(status_code=400, detail="Invalid 2FA token")
    current_user.google_2fa_enabled = 0
    current_user.google_2fa_secret = None
    _set_setting(db, "security.require_2fa", "false", "强制开启2FA", current_user.username)
    db.commit()
    invalidate_user_tokens(db, current_user)
    client_ip = request.client.host if request.client else None
    create_audit_log(
        db, username=current_user.username, action="2fa_disabled",
        resource_type="auth", detail="User disabled Google 2FA",
        ip_address=client_ip
    )
    return {"message": "2FA disabled successfully"}


@router.get("/status")
async def get_2fa_status(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    current_user, _ = await _resolve_effective_user(request, bearer_token, db)
    return {
        "enabled": int(getattr(current_user, "google_2fa_enabled", 0) or 0) == 1,
        "has_secret": bool(getattr(current_user, "google_2fa_secret", None))
    }
