import secrets
import hashlib
import hmac
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from ..database import get_db, TrafficChannel, LandingTemplate, Device, Log, create_audit_log, Agent
from ..auth import get_current_user
from .settings import require_module_2fa
from .. import config
from ._helpers import apply_agent_filter_channel, apply_agent_filter_template, _resolve_agent_scope
from ..config_constants import cfg_int


def _assert_owns_channel(db, user, c: TrafficChannel) -> None:
    if c is None:
        return
    scope, aid = _resolve_agent_scope(db, user)
    if scope == "admin" or aid is None:
        return
    if c.agent_id is None:
        raise HTTPException(403, "无权限访问该渠道")
    if int(c.agent_id) != int(aid):
        raise HTTPException(403, "无权限访问该渠道")

router = APIRouter(prefix="/api/channels", tags=["channels"], redirect_slashes=False)


class ChannelCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    color: Optional[str] = "#67c23a"
    domain_whitelist: Optional[str] = None
    default_template_id: Optional[int] = None
    enabled: Optional[bool] = True
    note: Optional[str] = None


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, min_length=2, max_length=64)
    color: Optional[str] = None
    domain_whitelist: Optional[str] = None
    default_template_id: Optional[int] = None
    enabled: Optional[bool] = None
    note: Optional[str] = None


class S2SRegisterRequest(BaseModel):
    device_uuid: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    host: Optional[str] = None
    referer: Optional[str] = None
    access_path: Optional[str] = None
    hw_model: Optional[str] = None
    template_id: Optional[int] = None
    ts: Optional[int] = None
    nonce: Optional[str] = None
    sign: Optional[str] = None


def _gen_api_key() -> str:
    return "ds_" + secrets.token_hex(24)


def _serialize(c: TrafficChannel, db: Session):
    d = {
        "id": c.id, "slug": c.slug, "name": c.name, "api_key": c.api_key,
        "color": c.color or "#67c23a", "domain_whitelist": c.domain_whitelist,
        "default_template_id": c.default_template_id,
        "enabled": int(c.enabled if c.enabled is not None else 1),
        "visit_count": int(c.visit_count or 0), "device_count": int(c.device_count or 0),
        "note": c.note, "created_by": c.created_by, "agent_id": c.agent_id, "agent_name": None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "default_template_name": None, "default_template_slug": None,
    }
    if c.default_template_id:
        try:
            t = db.query(LandingTemplate).filter(LandingTemplate.id == int(c.default_template_id)).first()
            if t:
                d["default_template_name"] = t.name
                d["default_template_slug"] = t.slug
        except Exception:
            pass
    if c.agent_id:
        try:
            a = db.query(Agent).filter(Agent.id == c.agent_id).first()
            if a:
                d["agent_name"] = a.name or a.username
        except Exception:
            pass
    try:
        d["device_count"] = int(db.query(func.count(Device.id)).filter(Device.channel_id == c.id).scalar() or 0)
    except Exception:
        pass
    return d


def _verify_sign(payload_body: bytes, api_key: str, body: S2SRegisterRequest, db: Session) -> bool:
    if not body.sign or not body.ts or not body.nonce:
        return False
    try:
        skew_allow = max(60, int(cfg_int(db, "auth.channel_ts_skew_sec")))
        if abs(int(body.ts) - int(datetime.now().timestamp())) > skew_allow:
            return False
    except Exception:
        return False
    body_dict = body.dict()
    body_dict.pop("sign", None)
    import json
    body_json_for_sign = json.dumps(body_dict, sort_keys=True)
    payload_digest = hashlib.sha256(body_json_for_sign.encode("utf-8")).hexdigest()
    msg = f"{body.ts}\n{body.nonce}\n{payload_digest}".encode("utf-8")
    expected = hmac.new(api_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, body.sign or "")


@router.get("")
async def list_channels(
    search: Optional[str] = None, enabled: Optional[bool] = None, agent_id: Optional[int] = None,
    skip: int = 0, limit: int = 200, sort: Optional[str] = "id", order: Optional[str] = "desc",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    q = db.query(TrafficChannel)
    q = apply_agent_filter_channel(q, db, current_user)
    if search and search.strip():
        kw = f"%{search.strip()}%"
        q = q.filter(or_(TrafficChannel.slug.like(kw), TrafficChannel.name.like(kw),
                         TrafficChannel.api_key.like(kw), TrafficChannel.domain_whitelist.like(kw)))
    if enabled is True:
        q = q.filter(TrafficChannel.enabled == 1)
    elif enabled is False:
        q = q.filter(TrafficChannel.enabled == 0)
    if agent_id is not None:
        if int(agent_id) <= 0:
            q = q.filter(TrafficChannel.agent_id.is_(None))
        else:
            q = q.filter(TrafficChannel.agent_id == int(agent_id))
    total = q.count()
    order_func = desc if (order or "desc").lower() != "asc" else None
    col = {"id": TrafficChannel.id, "created_at": TrafficChannel.created_at,
           "visit_count": TrafficChannel.visit_count, "device_count": TrafficChannel.device_count,
           "name": TrafficChannel.name, "slug": TrafficChannel.slug}.get((sort or "id").lower(), TrafficChannel.id)
    q = q.order_by(desc(col) if order_func else col.asc())
    rows = q.offset(skip).limit(limit).all()
    return {"total": total, "items": [_serialize(r, db) for r in rows]}


@router.get("/{channel_id}")
async def get_channel(channel_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = db.query(TrafficChannel).filter(TrafficChannel.id == int(channel_id)).first()
    if not c:
        raise HTTPException(404, "Channel not found")
    _assert_owns_channel(db, current_user, c)
    return _serialize(c, db)


@router.get("/slug/{slug}")
async def get_channel_by_slug(slug: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = db.query(TrafficChannel).filter(TrafficChannel.slug == slug).first()
    if not c:
        raise HTTPException(404, "Channel not found")
    _assert_owns_channel(db, current_user, c)
    return _serialize(c, db)


@router.post("")
async def create_channel(request: Request, payload: ChannelCreate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "channels", otp_code)
    slug = payload.slug.strip()
    if db.query(TrafficChannel).filter(TrafficChannel.slug == slug).first():
        raise HTTPException(400, "slug 已存在")
    c = TrafficChannel(
        slug=slug, name=payload.name.strip(), api_key=_gen_api_key(),
        color=payload.color or "#67c23a", domain_whitelist=payload.domain_whitelist,
        default_template_id=payload.default_template_id,
        enabled=1 if payload.enabled in (None, True) else 0,
        note=payload.note, created_by=getattr(current_user, "username", None),
        created_at=datetime.now(), updated_at=datetime.now(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="channel_create", resource_type="channel",
                     resource_id=str(c.id), detail=f"Created channel {c.slug}",
                     ip_address=request.client.host if request.client else None)
    return _serialize(c, db)


@router.patch("/{channel_id}")
async def update_channel(request: Request, channel_id: int, payload: ChannelUpdate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "channels", otp_code)
    c = db.query(TrafficChannel).filter(TrafficChannel.id == int(channel_id)).first()
    if not c:
        raise HTTPException(404, "Channel not found")
    _assert_owns_channel(db, current_user, c)
    if payload.name is not None: c.name = payload.name.strip()
    if payload.slug is not None:
        ns = payload.slug.strip()
        other = db.query(TrafficChannel).filter(TrafficChannel.slug == ns, TrafficChannel.id != c.id).first()
        if other: raise HTTPException(400, "slug 已存在")
        c.slug = ns
    if payload.color is not None: c.color = payload.color
    if payload.domain_whitelist is not None: c.domain_whitelist = payload.domain_whitelist
    if payload.default_template_id is not None: c.default_template_id = payload.default_template_id
    if payload.enabled is not None: c.enabled = 1 if payload.enabled else 0
    if payload.note is not None: c.note = payload.note
    c.updated_at = datetime.now()
    db.commit()
    db.refresh(c)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="channel_update", resource_type="channel",
                     resource_id=str(c.id), detail=f"Updated channel {c.slug}",
                     ip_address=request.client.host if request.client else None)
    return _serialize(c, db)


@router.post("/{channel_id}/rotate-key")
async def rotate_key(request: Request, channel_id: int, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "channels", otp_code)
    c = db.query(TrafficChannel).filter(TrafficChannel.id == int(channel_id)).first()
    if not c:
        raise HTTPException(404, "Channel not found")
    _assert_owns_channel(db, current_user, c)
    c.api_key = _gen_api_key()
    c.updated_at = datetime.now()
    db.commit()
    db.refresh(c)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="channel_rotate_key", resource_type="channel",
                     resource_id=str(c.id), detail=f"Rotated API key for {c.slug}",
                     ip_address=request.client.host if request.client else None)
    return _serialize(c, db)


@router.delete("/{channel_id}")
async def delete_channel(request: Request, channel_id: int, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "channels", otp_code)
    c = db.query(TrafficChannel).filter(TrafficChannel.id == int(channel_id)).first()
    if not c:
        raise HTTPException(404, "Channel not found")
    _assert_owns_channel(db, current_user, c)
    slug = c.slug
    db.delete(c)
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="channel_delete", resource_type="channel",
                     resource_id=str(channel_id), detail=f"Deleted channel {slug}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Channel deleted"}


@router.post("/{channel_id}/s2s-register")
async def s2s_register(request: Request, channel_id: int, body: S2SRegisterRequest, db: Session = Depends(get_db)):
    c = db.query(TrafficChannel).filter(TrafficChannel.id == int(channel_id)).first()
    if not c:
        raise HTTPException(404, "Channel not found")
    if c.enabled != 1:
        raise HTTPException(403, "Channel disabled")
    if not _verify_sign(await request.body(), c.api_key or "", body, db):
        raise HTTPException(401, "Invalid signature")
    from .devices import register_device as _rd
    from pydantic import BaseModel as _BM

    class _P:
        def __init__(self, **kw):
            for k, v in kw.items(): setattr(self, k, v)
        def dict(self): return self.__dict__
    p = _P(device_uuid=body.device_uuid, user_agent=body.user_agent, host=body.host,
           referer=body.referer, access_path=body.access_path, hw_model=body.hw_model,
           channel_id=c.id, template_id=body.template_id, extra={})
    p.force_is_new = False
    p.force_was_offline = False

    class _FakeRequest:
        def __init__(self, ip, ua):
            class _C: host = ip
            self.client = _C()
            self.headers = {"user-agent": ua or ""}
    fake_req = _FakeRequest(body.ip, body.user_agent)
    try:
        result = await _rd(fake_req, p, db)
    except Exception as e:
        raise HTTPException(500, f"Register failed: {e}")
    return {"ok": True, "data": result}


@router.get("/{channel_id}/embed")
async def get_embed_code(channel_id: int, mode: str = "iframe", public_base_url: Optional[str] = None, tpl_slug: Optional[str] = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    c = db.query(TrafficChannel).filter(TrafficChannel.id == int(channel_id)).first()
    if not c:
        raise HTTPException(404, "Channel not found")
    base = public_base_url or config.DARKSWORD_PUBLIC_BASE or "http://localhost:7070"
    base = base.rstrip("/")
    tpl_part = f"&tpl={urllib.parse.quote(tpl_slug)}" if tpl_slug else ""
    url = f"{base}/ch/{c.slug}?ch={c.slug}{tpl_part}"
    if mode == "script":
        code = f'<script src="{base}/ch/{c.slug}/embed.js?ch={urllib.parse.quote(c.slug)}{tpl_part}" async></script>'
    elif mode == "link":
        code = f'<a href="{url}" target="_blank" rel="noopener">访问链接</a>'
    else:
        code = f'<iframe src="{url}" width="100%" height="800" frameborder="0" allow="camera;microphone;geolocation"></iframe>'
    return {
        "mode": mode, "url": url, "code": code,
        "channel": {"id": c.id, "slug": c.slug, "name": c.name, "api_key_preview": (c.api_key or "")[:10] + "...", "default_template_id": c.default_template_id}
    }
