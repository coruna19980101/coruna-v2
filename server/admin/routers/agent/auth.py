from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ...database import get_db, Agent, Settings, create_audit_log
from ...agent_auth import authenticate_agent, create_agent_access_token, get_current_agent, invalidate_agent_tokens
from ...utils.totp import verify_totp
from ... import config
from ...limiter import rate_limit
from ...settings_manager import get_setting
from ...config_constants import cfg_int, rate_limit_for
import secrets

router = APIRouter(prefix="/api/agent/auth", tags=["agent-auth"], redirect_slashes=False)

ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES
_agent_pending_2fa = {}
_agent_pending_2fa_setup = {}


def _int_setting(db: Session, key: str, default: int) -> int:
    raw = get_setting(db, key, None)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _bool_setting(db: Session, key: str) -> bool:
    raw = get_setting(db, key, "false")
    return str(raw or "").strip().lower() in {"1", "true", "on", "yes", "y"}


def _cleanup_expired_pending(d: dict) -> None:
    now_ts = datetime.now().timestamp()
    expired_keys = [k for k, v in d.items() if v.get("expires_at", 0) < now_ts]
    for k in expired_keys:
        try:
            del d[k]
        except KeyError:
            pass


def _is_account_locked(entity):
    locked_until = getattr(entity, "locked_until", None)
    if locked_until is None:
        return False, None
    if isinstance(locked_until, str):
        try:
            locked_until = datetime.fromisoformat(locked_until)
        except Exception:
            return False, None
    now = datetime.now()
    if locked_until <= now:
        return False, None
    return True, max(int((locked_until - now).total_seconds()), 1)


class AgentVerify2FARequest(BaseModel):
    temp_token: str
    otp_code: str


@rate_limit(rate_limit_for("limits.auth_login_per_min"))
@rate_limit(config.AUTH_RATE_LIMIT)
@router.post("/login")
async def agent_login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    agent = authenticate_agent(db, form_data.username, form_data.password)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    if not agent:
        create_audit_log(
            db, username=f"agent:{form_data.username}", action="agent_login_failed",
            resource_type="agent_auth",
            detail=f"Agent failed login attempt from IP {client_ip}",
            ip_address=client_ip, user_agent=user_agent
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect agent username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ① 冻结检查
    locked, remain_sec = _is_account_locked(agent)
    if locked:
        remain_min = max(1, (remain_sec + 59) // 60)
        create_audit_log(
            db, username=f"agent:{agent.username}", action="agent_login_denied_locked",
            resource_type="agent_auth",
            detail=f"Agent login locked: {remain_min} min remaining, IP {client_ip}",
            ip_address=client_ip, user_agent=user_agent
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Agent locked due to too many failed 2FA attempts. Try again in {remain_min} minute(s)."
        )

    # ② 2FA 流程
    require_2fa = _bool_setting(db, "security.require_2fa")
    force_2fa_agents = _bool_setting(db, "security.force_2fa_agents")
    need_flow = require_2fa or force_2fa_agents
    _cleanup_expired_pending(_agent_pending_2fa)
    _cleanup_expired_pending(_agent_pending_2fa_setup)

    has_bound = (int(getattr(agent, "google_2fa_enabled", 0) or 0) == 1) and bool(getattr(agent, "google_2fa_secret", None))

    if need_flow and has_bound:
        temp_token = secrets.token_urlsafe(32)
        otp_ttl = cfg_int(db, "auth.otp_pending_ttl_sec")
        _agent_pending_2fa[temp_token] = {
            "username": agent.username,
            "expires_at": datetime.now().timestamp() + max(60, int(otp_ttl))
        }
        create_audit_log(
            db, username=f"agent:{agent.username}", action="agent_login_2fa_required",
            resource_type="agent_auth",
            detail=f"Agent requires 2FA verification from IP {client_ip}",
            ip_address=client_ip, user_agent=user_agent
        )
        return {"requires_2fa": True, "temp_token": temp_token, "message": "2FA required"}

    if need_flow and not has_bound:
        setup_token = secrets.token_urlsafe(32)
        setup_ttl = cfg_int(db, "auth.setup_token_ttl_sec")
        _agent_pending_2fa_setup[setup_token] = {
            "username": agent.username,
            "for_role": "agent",
            "agent_id": int(getattr(agent, "id", 0) or 0),
            "expires_at": datetime.now().timestamp() + max(60, int(setup_ttl))
        }
        create_audit_log(
            db, username=f"agent:{agent.username}", action="agent_login_2fa_binding_required",
            resource_type="agent_auth",
            detail=f"Force 2FA for agent: setup_temp_token issued, IP={client_ip}",
            ip_address=client_ip, user_agent=user_agent
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "TWO_FACTOR_BINDING_REQUIRED",
                "message": "系统已强制要求代理商启用 2FA，您尚未绑定。请先完成 2FA 绑定后再登录。",
                "requires_2fa_binding": True,
                "setup_temp_token": setup_token
            }
        )

    agent.last_login = datetime.now()
    agent.last_login_ip = client_ip
    agent.failed_2fa_attempts = 0
    agent.locked_until = None
    db.commit()
    create_audit_log(
        db, username=f"agent:{agent.username}", action="agent_login_success",
        resource_type="agent_auth",
        detail=f"Agent logged in from IP {client_ip}",
        ip_address=client_ip, user_agent=user_agent
    )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_agent_access_token(
        data={"sub": agent.username, "role": "agent", "agent_id": agent.id,
              "ver": getattr(agent, "token_version", 0) or 0, "type": "agent"},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "requires_2fa": False}


@rate_limit(rate_limit_for("limits.auth_2fa_per_min"))
@router.post("/verify-2fa")
async def agent_verify_2fa(request: Request, body: AgentVerify2FARequest, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else None
    _cleanup_expired_pending(_agent_pending_2fa)
    pending = _agent_pending_2fa.get(body.temp_token)
    if not pending:
        raise HTTPException(status_code=400, detail="Invalid temp token")
    if datetime.now().timestamp() > pending["expires_at"]:
        del _agent_pending_2fa[body.temp_token]
        raise HTTPException(status_code=400, detail="Temp token expired")
    agent = db.query(Agent).filter(Agent.username == pending["username"]).first()
    if not agent:
        if body.temp_token in _agent_pending_2fa:
            del _agent_pending_2fa[body.temp_token]
        raise HTTPException(status_code=400, detail="Agent not found")

    locked, remain = _is_account_locked(agent)
    if locked:
        remain_min = max(1, (remain + 59) // 60)
        if body.temp_token in _agent_pending_2fa:
            del _agent_pending_2fa[body.temp_token]
        raise HTTPException(status_code=423, detail=f"Account locked. {remain_min} minute(s) remaining.")

    if not verify_totp(agent.google_2fa_secret, body.otp_code):
        agent.failed_2fa_attempts = int(getattr(agent, "failed_2fa_attempts", 0) or 0) + 1
        threshold = _int_setting(db, "security.2fa_lock_after_attempts", 5)
        lock_minutes = _int_setting(db, "security.2fa_lock_minutes", 15)
        locked_now = threshold > 0 and agent.failed_2fa_attempts >= threshold
        if locked_now:
            agent.locked_until = datetime.now() + timedelta(minutes=lock_minutes)
            create_audit_log(
                db, username=f"agent:{agent.username}", action="agent_2fa_account_locked",
                resource_type="agent_auth",
                detail=f"Agent 2FA failures={agent.failed_2fa_attempts} (>= {threshold}). "
                       f"Locked for {lock_minutes} min from IP {client_ip}",
                ip_address=client_ip
            )
        else:
            create_audit_log(
                db, username=f"agent:{agent.username}", action="agent_login_2fa_failed",
                resource_type="agent_auth",
                detail=f"Agent 2FA verify failed #{agent.failed_2fa_attempts}/{threshold}, IP {client_ip}",
                ip_address=client_ip
            )
        db.commit()
        if body.temp_token in _agent_pending_2fa:
            del _agent_pending_2fa[body.temp_token]
        if locked_now:
            raise HTTPException(status_code=423,
                                detail=f"Too many failed 2FA attempts. Agent locked for {lock_minutes} minute(s).")
        raise HTTPException(status_code=400,
                            detail=f"Invalid 2FA code ({agent.failed_2fa_attempts}/{threshold}). "
                                   f"Lockout after {threshold} consecutive failures.")

    del _agent_pending_2fa[body.temp_token]
    agent.failed_2fa_attempts = 0
    agent.locked_until = None
    agent.last_login = datetime.now()
    agent.last_login_ip = client_ip
    db.commit()
    create_audit_log(
        db, username=f"agent:{agent.username}", action="agent_login_success",
        resource_type="agent_auth",
        detail=f"Agent logged in with 2FA from IP {client_ip}",
        ip_address=client_ip, user_agent=request.headers.get("user-agent")
    )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_agent_access_token(
        data={"sub": agent.username, "role": "agent", "agent_id": agent.id,
              "ver": getattr(agent, "token_version", 0) or 0, "type": "agent"},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def agent_me(current_agent: Agent = Depends(get_current_agent)):
    return {
        "id": current_agent.id, "username": current_agent.username,
        "name": current_agent.name, "contact": current_agent.contact,
        "phone": current_agent.phone, "enabled": int(current_agent.enabled if current_agent.enabled is not None else 1),
        "max_devices": current_agent.max_devices or 0,
        "commission_rate": current_agent.commission_rate or 0,
        "last_login": current_agent.last_login.isoformat() if current_agent.last_login else None,
        "created_at": current_agent.created_at.isoformat() if current_agent.created_at else None,
    }


@router.post("/logout")
async def agent_logout(
    request: Request,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    invalidate_agent_tokens(db, current_agent)
    return {"message": "Logged out successfully"}
