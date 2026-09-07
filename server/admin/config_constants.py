"""
All tunable constants for Coruna admin: defaults, env keys, setting keys.

Priority order when reading a value:
    1) environment variable (admin/.env → os.environ)
    2) database `settings` table (SQL table key)
    3) hardcoded default in this file (safe fallback, never 0/empty where safety-sensitive)

Why this file exists: we used to write magic numbers like 30, 90, 365, 03:30,
500, 5000, 600 directly into each module.  That makes testing / tuning / review
very hard.  From now on **every threshold, path, rate, batch size, time window
MUST have its single source of truth here** and lookups go through the helpers
below.

Frontend equivalent: coruna_admin_frontend/src/constants/paths.js (for route
string literals like '/login' '/dashboard').
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from sqlalchemy.orm import Session


# --------------------------------------------------------------------------- #
# Project roots (these are "structural" constants, not tunable settings; the
# real defaults we want to keep flexible start below.)
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_ROOT = PROJECT_ROOT / "admin"
DB_FILE = PROJECT_ROOT / "darksword.db"
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_ARCHIVE_DIR = PROJECT_ROOT / "logs_archive"
BACKUP_DIR = PROJECT_ROOT / "backup"
STATE_DIR = LOGS_ARCHIVE_DIR / ".state"  # stamp files for "already-run-today"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

DEFAULT_CORS_FALLBACK = [
    "http://localhost:7070", "http://localhost:5173", "http://localhost:3000",
]


# --------------------------------------------------------------------------- #
# Canonical defaults table (single source of truth)
#   (setting_key_in_db, env_key, default_value, description)
# --------------------------------------------------------------------------- #
DEFAULTS: Tuple[Tuple[str, Optional[str], Any, str], ...] = (
    # ───────── Retention / cleanup ─────────
    ("retention.log_days",            "RETENTION_LOG_DAYS",             30,  "访问日志(logs表)保留天数，超时先gz归档到logs_archive/再删除"),
    ("retention.audit_days",          "RETENTION_AUDIT_DAYS",           90,  "审计日志(audit_logs表)保留天数，超时先gz归档再删除"),
    ("retention.exfil_days",          "RETENTION_EXFIL_DAYS",          365,  "设备采集数据(exfil_data表)保留天数，超时直接删除(不归档)"),
    ("retention.fs_log_days",         "RETENTION_FS_LOG_DAYS",          30,  "磁盘logs/目录下日志文件保留天数，超时压缩到logs_archive/"),
    ("retention.archive_batch_rows",  "RETENTION_ARCHIVE_BATCH",      5000,  "日志归档单次SELECT批次行数(内存/IO折中)"),
    ("retention.delete_chunk_rows",   "RETENTION_DELETE_CHUNK",        500,  "批量IN删除的chunk大小(SQLite变量上限安全值)"),
    ("retention.exfil_delete_chunk_rows", "RETENTION_EXFIL_DELETE_CHUNK", 1000, "exfil_data批量DELETE每批行数，过大触发too many SQL variables"),
    ("retention.backup_keep_days",    "RETENTION_BACKUP_KEEP_DAYS",     14,  "backup/目录下数据库备份文件保留天数"),

    # ───────── Scheduled jobs (lifespan 守护协程) ─────────
    ("cron.rotate_start_hhmm",        "CRON_ROTATE_START",          "03:30",  "日志轮转窗口起始 HH:mm；窗口内每分钟 tick 一次，直到成功(通过 stamp 文件避免重复)"),
    ("cron.rotate_window_minutes",    "CRON_ROTATE_WINDOW_MIN",        10,  "日志轮转自起始时间起允许执行的窗口分钟数(错过窗口需手动或等到次日)"),
    ("cron.rotate_tick_seconds",      "CRON_ROTATE_TICK_SEC",          60,  "日志轮转守护协程轮询间隔(秒)"),
    ("cron.cmd_timeout_minutes",      "CRON_CMD_TIMEOUT_MIN",          30,  "commands.executing超过N分钟未完成则自动置为timeout"),
    ("cron.cmd_timeout_tick_seconds", "CRON_CMD_TICK_SEC",            300,  "命令超时守护协程轮询间隔(秒)"),

    # ───────── Auth / 2FA / session ─────────
    ("auth.otp_pending_ttl_sec",      "AUTH_OTP_PENDING_TTL",         300,  "登录+2FA时第一次密码通过后，pending 2FA验证token的TTL(秒)"),
    ("auth.setup_token_ttl_sec",      "AUTH_SETUP_TOKEN_TTL",         600,  "强制2FA下发给未绑定用户的setup_temp_token TTL(秒)"),
    ("auth.channel_ts_skew_sec",      "AUTH_CHANNEL_TS_SKEW",         300,  "渠道上报register时ts字段允许的时钟偏差(秒)"),
    ("auth.active_device_minutes",    "AUTH_ACTIVE_DEVICE_MIN",        30,  "仪表盘/设备列表里「在线设备」判定的最近活跃分钟阈值"),
    ("auth.dashboard_max_days",       "AUTH_DASH_MAX_DAYS",            90,  "仪表盘图表区间上限(天)，超过自动截断防慢查询"),

    # ───────── Rate limits (slowapi + @rate_limit 双重) ─────────
    ("limits.auth_login_per_min",     "LIMIT_AUTH_LOGIN",                5,  "登录(/api/auth/token)每IP每分钟最大尝试次数(防爆破)"),
    ("limits.auth_2fa_per_min",       "LIMIT_AUTH_2FA",                 30,  "2FA验证/绑定相关接口每用户每分钟上限"),
    ("limits.auth_send_otp_per_min",  "LIMIT_AUTH_SEND_OTP",             3,  "发送OTP(预留短信/邮件)每IP每分钟上限"),
    ("limits.cmd_send_per_min",       "LIMIT_CMD_SEND",                180,  "下发命令每用户每分钟上限"),
    ("limits.cmd_bulk_per_min",       "LIMIT_CMD_BULK",                 10,  "批量命令/批量操作每用户每分钟上限"),
    ("limits.tfa_setup_per_min",      "LIMIT_TFA_SETUP",                10,  "2FA setup接口每用户每分钟上限"),
    ("limits.tfa_verify_test_per_min","LIMIT_TFA_VERIFY_TEST",           5,  "2FA verify-test接口每用户每分钟上限"),

    # ───────── Device / exploit side ─────────
    ("device.cookie_max_age_sec",     "DEVICE_COOKIE_MAX_AGE",   60*60*24*30,  "渠道落地页设备Cookie Max-Age(秒)，默认30天"),
    ("device.log_tail_lines",         "DEVICE_LOG_TAIL_LINES",   500,           "漏洞服务器自带/logs查看页默认显示的尾部行数"),
    ("device.sanitize_path_max",      "DEVICE_SANITIZE_PATH_MAX",500,           "sanitize_path 对URL/path输入的最大字符数(>截断防栈溢出)"),
    ("device.exfil_desc_max",         "DEVICE_EXFIL_DESC_MAX",   500,           "exfil_data.description字段写入前自动截断的最大字符数"),

    # ───────── Pagination (所有列表接口的上限) ─────────
    ("page.default_limit",            "PAGE_DEFAULT_LIMIT",      100,  "列表默认limit"),
    ("page.max_limit",                "PAGE_MAX_LIMIT",          500,  "列表允许的最大limit(超过自动截断防OOM)"),

    # ───────── Frontend route defaults (后端返回给前端，前端常量同步) ─────────
    ("fe.route_login",                "FE_ROUTE_LOGIN",        "/login",     "前端登录页path(两边同步改即可)"),
    ("fe.route_dashboard",            "FE_ROUTE_DASHBOARD",    "/dashboard", "前端登录成功后默认落地页path"),
)


# --------------------------------------------------------------------------- #
# Simple env readers (type coercion + fallback)
# --------------------------------------------------------------------------- #
def _coerce_bool(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def env_str(key: Optional[str], default: str) -> str:
    if not key:
        return default
    v = os.getenv(key)
    return v if (v is not None and v != "") else default


def env_int(key: Optional[str], default: int) -> int:
    if not key:
        return default
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def env_bool(key: Optional[str], default: bool) -> bool:
    if not key:
        return default
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    return _coerce_bool(raw)


# --------------------------------------------------------------------------- #
# "Setting key -> metadata" lookup index built from DEFAULTS above
# --------------------------------------------------------------------------- #
_BY_SETTING_KEY: dict = {row[0]: {"env": row[1], "default": row[2], "doc": row[3]} for row in DEFAULTS}


def get_meta(setting_key: str) -> Optional[dict]:
    return _BY_SETTING_KEY.get(setting_key)


def default_of(setting_key: str) -> Any:
    return (_BY_SETTING_KEY[setting_key]["default"]
            if setting_key in _BY_SETTING_KEY else None)


def all_setting_keys() -> list[str]:
    return [r[0] for r in DEFAULTS]


def parse_hhmm(hhmm: str) -> Tuple[int, int]:
    """Parse 'HH:mm' -> (hour, minute).  Raises ValueError on malformed."""
    if not hhmm or ":" not in hhmm:
        raise ValueError(f"Invalid HH:mm: {hhmm!r}")
    h, m = hhmm.split(":", 1)
    hi, mi = int(h), int(m)
    if not (0 <= hi <= 23 and 0 <= mi <= 59):
        raise ValueError(f"Out-of-range HH:mm: {hhmm!r}")
    return hi, mi


# --------------------------------------------------------------------------- #
# Priority-aware typed getters.  If you pass a Session, we consult settings
# table; otherwise we fall back to env-only (good for CLI tools).
# --------------------------------------------------------------------------- #
def _with_settings(db: Optional[Session],
                   setting_key: str,
                   env_key: Optional[str],
                   default: Any,
                   coerce: Callable[[str], Any]) -> Any:
    """Priority: env > settings table > default."""
    # 1) env (top priority: operators often put secrets / per-deploy tweaks there)
    if env_key:
        raw_env = os.getenv(env_key)
        if raw_env is not None and raw_env != "":
            return coerce(raw_env)
    # 2) DB settings
    if db is not None:
        from .routers.settings import _get_setting  # avoid circular import
        raw_db = _get_setting(db, setting_key, "")
        if raw_db != "":
            try:
                return coerce(raw_db)
            except (TypeError, ValueError):
                pass
    # 3) fallback
    return default


def cfg_int(db: Optional[Session], setting_key: str) -> int:
    meta = _BY_SETTING_KEY.get(setting_key)
    if not meta:
        raise KeyError(f"Unknown setting key: {setting_key}")
    return _with_settings(db, setting_key, meta["env"], int(meta["default"]),
                          coerce=lambda s: int(str(s).strip()))


def cfg_str(db: Optional[Session], setting_key: str) -> str:
    meta = _BY_SETTING_KEY.get(setting_key)
    if not meta:
        raise KeyError(f"Unknown setting key: {setting_key}")
    return _with_settings(db, setting_key, meta["env"], str(meta["default"]),
                          coerce=lambda s: str(s))


def cfg_bool(db: Optional[Session], setting_key: str) -> bool:
    meta = _BY_SETTING_KEY.get(setting_key)
    if not meta:
        raise KeyError(f"Unknown setting key: {setting_key}")
    return _with_settings(db, setting_key, meta["env"], bool(meta["default"]),
                          coerce=_coerce_bool)


def cfg_rate_str(db: Optional[Session], setting_key: str) -> str:
    """Return a slowapi-compatible rate string like '5/minute' from an int limit."""
    return f"{cfg_int(db, setting_key)}/minute"


def rate_limit_for(setting_key: str) -> str:
    """Shortcut for decorator-time evaluation (db not available yet) → env or default only."""
    return cfg_rate_str(None, setting_key)
