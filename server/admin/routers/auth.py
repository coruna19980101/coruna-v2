from datetime import timedelta, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
import secrets

from ..database import get_db, User, init_db, create_audit_log, Settings
from ..auth import (
    authenticate_user, create_access_token, get_password_hash,
    get_current_user, invalidate_user_tokens, ADMIN_COOKIE_NAME,
)
from ..utils.totp import verify_totp
from ..schemas import Token, UserResponse
from .. import config
from ..limiter import rate_limit
from ..settings_manager import get_setting
from ..config_constants import cfg_int, rate_limit_for

router = APIRouter(prefix="/api/auth", tags=["auth"], redirect_slashes=False)

ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES
_pending_2fa = {}
_pending_2fa_setup = {}


def _token_response(access_token: str, expires_minutes: int, extra: dict = None) -> JSONResponse:
    body = {
        "access_token": access_token,
        "token_type": "bearer",
    }
    if extra:
        body.update(extra)
    resp = JSONResponse(body)
    max_age = max(60, int(expires_minutes) * 60)
    resp.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=access_token,
        max_age=max_age,
        expires=max_age,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return resp


def _get_int_setting(db: Session, key: str, default: int) -> int:
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


def _is_account_locked(entity) -> tuple[bool, Optional[int]]:
    """Return (is_locked, seconds_remaining)"""
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
    remain_sec = int((locked_until - now).total_seconds())
    return True, max(remain_sec, 1)


class Verify2FARequest(BaseModel):
    temp_token: str
    otp_code: str


@rate_limit(rate_limit_for("limits.auth_login_per_min"))
@rate_limit(config.AUTH_RATE_LIMIT)
@router.post("/login")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    if not user:
        create_audit_log(
            db, username=form_data.username, action="login_failed",
            resource_type="auth", detail=f"Failed login attempt from IP {client_ip}",
            ip_address=client_ip, user_agent=user_agent
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ① 账号冻结检查（达到 2FA 失败阈值自动冻结）
    locked, remain = _is_account_locked(user)
    if locked:
        remain_min = max(1, (remain + 59) // 60)
        create_audit_log(
            db, username=user.username, action="login_denied_locked",
            resource_type="auth",
            detail=f"Login denied due to 2FA lockout. Remaining: {remain_min} min, IP: {client_ip}",
            ip_address=client_ip, user_agent=user_agent
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked due to too many failed 2FA attempts. Try again in {remain_min} minute(s)."
        )

    # ② 2FA 要求：旧的 require_2fa 开关 OR 新的 force_2fa_users 开关任一为真即开启
    require_2fa = _bool_setting(db, "security.require_2fa")
    force_2fa_users = _bool_setting(db, "security.force_2fa_users")
    need_2fa_flow = require_2fa or force_2fa_users
    _cleanup_expired_pending(_pending_2fa)
    _cleanup_expired_pending(_pending_2fa_setup)

    has_bound_2fa = (int(getattr(user, "google_2fa_enabled", 0) or 0) == 1) and bool(getattr(user, "google_2fa_secret", None))

    if need_2fa_flow and has_bound_2fa:
        temp_token = secrets.token_urlsafe(32)
        otp_ttl = cfg_int(db, "auth.otp_pending_ttl_sec")
        _pending_2fa[temp_token] = {
            "username": user.username,
            "expires_at": datetime.now().timestamp() + max(60, int(otp_ttl))
        }
        create_audit_log(
            db, username=user.username, action="login_2fa_required",
            resource_type="auth", detail=f"User requires 2FA verification from IP {client_ip}",
            ip_address=client_ip, user_agent=user_agent
        )
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
            "message": "2FA verification required"
        }

    if need_2fa_flow and not has_bound_2fa:
        setup_token = secrets.token_urlsafe(32)
        setup_ttl = cfg_int(db, "auth.setup_token_ttl_sec")
        _pending_2fa_setup[setup_token] = {
            "username": user.username,
            "for_role": getattr(user, "role", "user"),
            "expires_at": datetime.now().timestamp() + max(60, int(setup_ttl))
        }
        create_audit_log(
            db, username=user.username, action="login_2fa_binding_required",
            resource_type="auth",
            detail=f"System forced 2FA. User must bind 2FA (setup_temp_token issued), IP={client_ip}",
            ip_address=client_ip, user_agent=user_agent
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "TWO_FACTOR_BINDING_REQUIRED",
                "message": "该系统已强制启用两步验证（2FA），您尚未绑定 2FA。请先完成 2FA 绑定后再登录。",
                "requires_2fa_binding": True,
                "setup_temp_token": setup_token
            }
        )

    user.last_login = datetime.now()
    user.last_login_ip = client_ip
    user.failed_2fa_attempts = 0
    user.locked_until = None
    db.commit()

    create_audit_log(
        db, username=user.username, action="login_success",
        resource_type="auth", detail=f"User logged in from IP {client_ip}",
        ip_address=client_ip, user_agent=user_agent
    )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "ver": getattr(user, "token_version", 0) or 0, "type": "admin"},
        expires_delta=access_token_expires
    )
    return _token_response(access_token, ACCESS_TOKEN_EXPIRE_MINUTES, {"requires_2fa": False})


@rate_limit(rate_limit_for("limits.auth_2fa_per_min"))
@router.post("/verify-2fa")
async def verify_login_2fa(
    request: Request,
    body: Verify2FARequest,
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else None
    _cleanup_expired_pending(_pending_2fa)
    pending = _pending_2fa.get(body.temp_token)
    if not pending:
        raise HTTPException(status_code=400, detail="Invalid or expired temp token")
    if datetime.now().timestamp() > pending["expires_at"]:
        del _pending_2fa[body.temp_token]
        raise HTTPException(status_code=400, detail="Temp token expired")

    user = db.query(User).filter(User.username == pending["username"]).first()
    if not user:
        del _pending_2fa[body.temp_token]
        raise HTTPException(status_code=400, detail="User not found")

    # 冻结状态重复检查，避免锁期内继续尝试
    locked, remain = _is_account_locked(user)
    if locked:
        remain_min = max(1, (remain + 59) // 60)
        if body.temp_token in _pending_2fa:
            del _pending_2fa[body.temp_token]
        raise HTTPException(status_code=423, detail=f"Account locked. {remain_min} minute(s) remaining.")

    if not verify_totp(user.google_2fa_secret, body.otp_code):
        user.failed_2fa_attempts = int(getattr(user, "failed_2fa_attempts", 0) or 0) + 1
        threshold = _get_int_setting(db, "security.2fa_lock_after_attempts", 5)
        lock_minutes = _get_int_setting(db, "security.2fa_lock_minutes", 15)
        locked_now = user.failed_2fa_attempts >= threshold > 0
        if locked_now:
            user.locked_until = datetime.now() + timedelta(minutes=lock_minutes)
            create_audit_log(
                db, username=user.username, action="2fa_account_locked",
                resource_type="auth",
                detail=f"2FA failures hit {user.failed_2fa_attempts} (>= {threshold}). "
                       f"Account locked for {lock_minutes} min from IP {client_ip}",
                ip_address=client_ip
            )
        else:
            create_audit_log(
                db, username=user.username, action="login_2fa_failed",
                resource_type="auth",
                detail=f"2FA verification failed (#{user.failed_2fa_attempts}/{threshold}) from IP {client_ip}",
                ip_address=client_ip
            )
        db.commit()
        if body.temp_token in _pending_2fa:
            del _pending_2fa[body.temp_token]
        if locked_now:
            raise HTTPException(status_code=423,
                                detail=f"Too many failed 2FA attempts. Account locked for {lock_minutes} minute(s).")
        raise HTTPException(status_code=400,
                            detail=f"Invalid 2FA code ({user.failed_2fa_attempts}/{threshold}). "
                                   f"You will be locked out after {threshold} consecutive failures.")

    # 验证成功：清零失败计数 + 解除冻结
    del _pending_2fa[body.temp_token]
    user.failed_2fa_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now()
    user.last_login_ip = client_ip
    db.commit()

    create_audit_log(
        db, username=user.username, action="login_success",
        resource_type="auth", detail=f"User logged in with 2FA from IP {client_ip}",
        ip_address=client_ip, user_agent=request.headers.get("user-agent")
    )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "ver": getattr(user, "token_version", 0) or 0, "type": "admin"},
        expires_delta=access_token_expires
    )
    return _token_response(access_token, ACCESS_TOKEN_EXPIRE_MINUTES)


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else None
    invalidate_user_tokens(db, current_user)
    create_audit_log(
        db, username=current_user.username, action="logout",
        resource_type="auth", detail=f"User logged out from IP {client_ip}",
        ip_address=client_ip, user_agent=request.headers.get("user-agent")
    )
    try:
        response.delete_cookie(key=ADMIN_COOKIE_NAME, path="/", httponly=True, samesite="lax")
    except Exception:
        pass
    return {"message": "Logged out successfully"}


@router.post("/init")
@rate_limit(rate_limit_for("limits.auth_send_otp_per_min"))
async def init_admin(request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else None
    allowed_hosts = {"127.0.0.1", "::1", "localhost"}
    if client_ip not in allowed_hosts:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin init only allowed from localhost. Please access via 127.0.0.1 / ::1."
        )
    existing_any = db.query(User).first()
    if existing_any is not None:
        init_db()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin already initialized. If you forgot password, reset via DB directly."
        )
    init_db()
    admin = User(username="admin", password=get_password_hash("admin123"), role="admin")
    db.add(admin)
    db.commit()
    db.refresh(admin)
    create_audit_log(
        db, username="system", action="admin_init",
        resource_type="auth",
        detail=f"Default admin created from IP {client_ip}. Please change password immediately.",
        ip_address=client_ip
    )
    return {"message": "Admin user created (change password immediately!)", "user": admin.username}
