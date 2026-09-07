from datetime import timedelta, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db, Agent, create_audit_log
from ...agent_auth import (
    get_current_agent as _auth_get_current_agent,
    invalidate_agent_tokens,
    create_agent_access_token,
)
from ...utils.totp import generate_secret, verify_totp, get_provisioning_uri
from ...limiter import rate_limit
from ...config_constants import rate_limit_for

try:
    from .auth import _agent_pending_2fa_setup as _agent_setup_tokens
except Exception:
    _agent_setup_tokens = {}

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8

router = APIRouter(prefix="/api/agent/2fa", tags=["agent-2fa"], redirect_slashes=False)

_opt_bearer = OAuth2PasswordBearer(tokenUrl="api/agent/auth/login", auto_error=False)


def _resolve_agent_by_setup_token(request: Request, db: Session):
    raw_token = (
        request.headers.get("X-Setup-Token")
        or request.headers.get("x-setup-token")
        or request.query_params.get("setup_token")
    )
    if not raw_token:
        return None, None, "missing-setup-token"
    now_ts = datetime.now().timestamp()
    key = str(raw_token).strip()
    item = _agent_setup_tokens.get(key)
    if not item or item.get("expires_at", 0) < now_ts:
        return None, None, "expired-setup-token"
    username = item.get("username")
    if not username:
        return None, None, "invalid-setup-token"
    agent = db.query(Agent).filter(Agent.username == username).first()
    if not agent:
        return None, None, "agent-not-found"
    return agent, key, None


async def _resolve_effective_agent(
    request: Request,
    bearer_token: Optional[str],
    db: Session,
):
    if bearer_token:
        try:
            agent = await _auth_get_current_agent(token=bearer_token, db=db)
            if agent is not None:
                return agent, None
        except HTTPException:
            pass
    agent, setup_tok, err = _resolve_agent_by_setup_token(request, db)
    if agent is None:
        if bearer_token is None and setup_tok is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        raise HTTPException(status_code=401, detail=f"Invalid credentials: {err or 'unknown'}")
    return agent, setup_tok


class Enable2FARequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=6)


class Verify2FARequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=6)


@router.get("/setup")
@rate_limit(rate_limit_for("limits.tfa_setup_per_min"))
async def agent_setup_2fa(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    agent_obj, used_setup_token = await _resolve_effective_agent(request, bearer_token, db)
    if int(getattr(agent_obj, "google_2fa_enabled", 0) or 0) == 1:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    secret = generate_secret()
    uri = get_provisioning_uri(secret, agent_obj.username)
    agent_obj.google_2fa_secret = secret
    agent_obj.google_2fa_enabled = 0
    db.commit()
    resp = {"secret": secret, "provisioning_uri": uri, "username": agent_obj.username}
    if used_setup_token:
        resp["setup_temp_token"] = used_setup_token
    return resp


@router.post("/enable")
@rate_limit(rate_limit_for("limits.tfa_setup_per_min"))
async def agent_enable_2fa(
    request: Request,
    body: Enable2FARequest,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    agent_obj, used_setup_token = await _resolve_effective_agent(request, bearer_token, db)
    client_ip = request.client.host if request.client else None
    if int(getattr(agent_obj, "google_2fa_enabled", 0) or 0) == 1:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    if not getattr(agent_obj, "google_2fa_secret", None):
        raise HTTPException(status_code=400, detail="Please call /setup first to generate a secret")
    if not verify_totp(agent_obj.google_2fa_secret, body.token):
        raise HTTPException(status_code=400, detail="Invalid 2FA token")
    agent_obj.google_2fa_enabled = 1
    agent_obj.failed_2fa_attempts = 0
    agent_obj.locked_until = None
    agent_obj.last_login = datetime.now()
    if client_ip:
        agent_obj.last_login_ip = client_ip
    db.commit()
    create_audit_log(
        db, username=f"agent:{agent_obj.username}", action="agent_2fa_enabled",
        resource_type="agent_auth", detail="Agent enabled Google 2FA",
        ip_address=client_ip
    )
    resp = {"message": "2FA enabled successfully"}
    if used_setup_token and used_setup_token in _agent_setup_tokens:
        del _agent_setup_tokens[used_setup_token]
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_agent_access_token(
            data={"sub": agent_obj.username, "role": "agent", "agent_id": int(getattr(agent_obj, "id", 0) or 0),
                  "ver": getattr(agent_obj, "token_version", 0) or 0, "type": "agent"},
            expires_delta=access_token_expires
        )
        resp["access_token"] = access_token
        resp["token_type"] = "bearer"
    return resp


@router.post("/verify")
@rate_limit(rate_limit_for("limits.auth_2fa_per_min"))
async def agent_verify_2fa(
    request: Request,
    body: Verify2FARequest,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    current_agent, _ = await _resolve_effective_agent(request, bearer_token, db)
    if int(getattr(current_agent, "google_2fa_enabled", 0) or 0) != 1 or not getattr(current_agent, "google_2fa_secret", None):
        raise HTTPException(status_code=400, detail="2FA not enabled")
    if not verify_totp(current_agent.google_2fa_secret, body.token):
        raise HTTPException(status_code=400, detail="Invalid 2FA token")
    return {"valid": True}


@router.post("/disable")
@rate_limit(rate_limit_for("limits.tfa_verify_test_per_min"))
async def agent_disable_2fa(
    request: Request,
    body: Verify2FARequest,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    current_agent, used_setup = await _resolve_effective_agent(request, bearer_token, db)
    if used_setup:
        raise HTTPException(status_code=403, detail="Must be fully authenticated to disable 2FA")
    if int(getattr(current_agent, "google_2fa_enabled", 0) or 0) != 1:
        raise HTTPException(status_code=400, detail="2FA not enabled")
    if not verify_totp(current_agent.google_2fa_secret, body.token):
        raise HTTPException(status_code=400, detail="Invalid 2FA token")
    current_agent.google_2fa_enabled = 0
    current_agent.google_2fa_secret = None
    db.commit()
    invalidate_agent_tokens(db, current_agent)
    client_ip = request.client.host if request.client else None
    create_audit_log(
        db, username=f"agent:{current_agent.username}", action="agent_2fa_disabled",
        resource_type="agent_auth", detail="Agent disabled Google 2FA",
        ip_address=client_ip
    )
    return {"message": "2FA disabled successfully"}


@router.get("/status")
async def agent_2fa_status(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(_opt_bearer),
):
    current_agent, _ = await _resolve_effective_agent(request, bearer_token, db)
    return {
        "enabled": int(getattr(current_agent, "google_2fa_enabled", 0) or 0) == 1,
        "has_secret": bool(getattr(current_agent, "google_2fa_secret", None))
    }
