from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime
from typing import Optional, List

from ..database import get_db, Agent, Device, TrafficChannel, LandingTemplate, DeviceGroup, create_audit_log
from ..auth import get_current_user, requires_role, get_password_hash, invalidate_user_tokens
from ..schemas import AgentCreate, AgentUpdate, AgentResetPassword, AgentResponse, AssignDataRequest, AssignChannelsRequest
from ..limiter import rate_limit
from .settings import require_module_2fa

router = APIRouter(prefix="/api/agents", tags=["agents"], redirect_slashes=False)


def _normalize_agent(a, db: Session, include_channels: bool = False):
    device_count = db.query(func.count(Device.id)).filter(Device.agent_id == a.id).scalar() or 0
    channels_query = db.query(TrafficChannel).filter(TrafficChannel.agent_id == a.id)
    channels_count = channels_query.count() or 0
    channel_ids = []
    if include_channels:
        channel_ids = [c.id for c in channels_query.all()]
    enabled_val = int(a.enabled if a.enabled is not None else 1)
    commission_rate_val = a.commission_rate or 0
    commission_rate_pct = commission_rate_val if commission_rate_val > 1 else commission_rate_val * 100
    max_devices_val = a.max_devices or 0
    return {
        "id": a.id,
        "username": a.username,
        "name": a.name,
        "contact": a.contact,
        "email": a.contact,
        "phone": a.phone,
        "enabled": enabled_val == 1,
        "enabled_int": enabled_val,
        "max_devices": max_devices_val,
        "device_quota": max_devices_val,
        "commission_rate": commission_rate_val,
        "commission": round(commission_rate_val / 100.0, 4) if commission_rate_val > 1 else commission_rate_val,
        "notes": a.notes,
        "remark": a.notes,
        "last_login": a.last_login.isoformat() if a.last_login else None,
        "last_login_ip": a.last_login_ip,
        "last_ip": a.last_login_ip,
        "google_2fa_enabled": int(a.google_2fa_enabled or 0),
        "twofa_enabled": bool(a.google_2fa_enabled),
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        "device_count": int(device_count),
        "channels_count": int(channels_count),
        "channel_ids": channel_ids,
    }


@router.get("")
@requires_role("admin")
async def list_agents(
    skip: int = 0, limit: int = 100,
    page: Optional[int] = None, page_size: Optional[int] = None,
    search: Optional[str] = None, q: Optional[str] = None,
    enabled: Optional[bool] = None, sort: Optional[str] = "id", order: Optional[str] = "desc",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    if page and page_size and skip == 0:
        skip = (page - 1) * page_size
        limit = page_size
    use_search = search or q
    query = db.query(Agent)
    if use_search and use_search.strip():
        kw = f"%{use_search.strip()}%"
        query = query.filter(
            (Agent.username.like(kw)) |
            (Agent.name.like(kw)) |
            (Agent.contact.like(kw)) |
            (Agent.phone.like(kw))
        )
    if enabled is True:
        query = query.filter(Agent.enabled == 1)
    elif enabled is False:
        query = query.filter(Agent.enabled == 0)
    total = query.count()
    order_func = desc if (order or "desc").lower() != "asc" else None
    col_map = {"id": Agent.id, "username": Agent.username, "name": Agent.name,
               "created_at": Agent.created_at, "last_login": Agent.last_login, "enabled": Agent.enabled}
    col = col_map.get((sort or "id").lower(), Agent.id)
    query = query.order_by(desc(col) if order_func else col.asc())
    rows = query.offset(skip).limit(limit).all()
    items = [_normalize_agent(a, db, include_channels=True) for a in rows]
    return {"total": total, "items": items, "skip": skip, "limit": limit}


@router.get("/{agent_id}")
@requires_role("admin")
async def get_agent(agent_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    a = db.query(Agent).filter(Agent.id == int(agent_id)).first()
    if not a:
        raise HTTPException(404, "Agent not found")
    return _normalize_agent(a, db, include_channels=True)


def _resolve_agent_payload_fields(payload):
    data = {}
    data["contact"] = payload.contact if getattr(payload, "contact", None) is not None else (
        payload.email if getattr(payload, "email", None) is not None else None)
    data["max_devices"] = payload.max_devices if getattr(payload, "max_devices", None) is not None else (
        payload.device_quota if getattr(payload, "device_quota", None) is not None else None)
    comm_rate = None
    if getattr(payload, "commission_rate", None) is not None:
        comm_rate = payload.commission_rate
    elif getattr(payload, "commission", None) is not None:
        c = payload.commission
        comm_rate = int(round(c * 100)) if 0 <= c <= 1 else int(round(c))
    data["commission_rate"] = comm_rate
    data["notes"] = payload.notes if getattr(payload, "notes", None) is not None else (
        payload.remark if getattr(payload, "remark", None) is not None else None)
    enabled_val = None
    if getattr(payload, "enabled", None) is not None:
        enabled_val = 1 if payload.enabled else 0
    data["enabled"] = enabled_val
    return data


@router.post("")
@requires_role("admin")
async def create_agent(request: Request, payload: AgentCreate, otp_code: str = "",
                       db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "agents", otp_code)
    if db.query(Agent).filter(Agent.username == payload.username).first():
        raise HTTPException(400, "代理商用户名已存在")
    if not payload.password or len(payload.password) < 6:
        raise HTTPException(400, "密码长度至少 6 位")
    fields = _resolve_agent_payload_fields(payload)
    a = Agent(
        username=payload.username,
        password=get_password_hash(payload.password),
        name=payload.name,
        contact=fields["contact"],
        phone=payload.phone,
        enabled=fields["enabled"] if fields["enabled"] is not None else 1,
        max_devices=fields["max_devices"] if fields["max_devices"] is not None else 0,
        commission_rate=fields["commission_rate"] if fields["commission_rate"] is not None else 0,
        notes=fields["notes"],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="agent_create", resource_type="agent",
                     resource_id=str(a.id), detail=f"Created agent {a.username}",
                     ip_address=request.client.host if request.client else None)
    return _normalize_agent(a, db)


@router.patch("/{agent_id}")
@requires_role("admin")
async def update_agent(request: Request, agent_id: int, payload: AgentUpdate, otp_code: str = "",
                       db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "agents", otp_code)
    a = db.query(Agent).filter(Agent.id == int(agent_id)).first()
    if not a:
        raise HTTPException(404, "Agent not found")
    fields = _resolve_agent_payload_fields(payload)
    if payload.name is not None:
        a.name = payload.name
    if payload.phone is not None:
        a.phone = payload.phone
    if fields["contact"] is not None:
        a.contact = fields["contact"]
    if fields["max_devices"] is not None:
        a.max_devices = fields["max_devices"]
    if fields["commission_rate"] is not None:
        a.commission_rate = fields["commission_rate"]
    if fields["notes"] is not None:
        a.notes = fields["notes"]
    if fields["enabled"] is not None:
        a.enabled = fields["enabled"]
        if a.enabled == 0:
            invalidate_user_tokens(db, a)
    a.updated_at = datetime.now()
    db.commit()
    db.refresh(a)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="agent_update", resource_type="agent",
                     resource_id=str(a.id), detail=f"Updated agent {a.username}",
                     ip_address=request.client.host if request.client else None)
    return _normalize_agent(a, db)


@router.post("/{agent_id}/reset-password")
@requires_role("admin")
async def reset_agent_password(request: Request, agent_id: int, body: AgentResetPassword, otp_code: str = "",
                               db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "agents", otp_code)
    a = db.query(Agent).filter(Agent.id == int(agent_id)).first()
    if not a:
        raise HTTPException(404, "Agent not found")
    new_pwd = body.new_password or body.password
    if not new_pwd or len(new_pwd) < 6:
        raise HTTPException(400, "密码长度至少 6 位")
    a.password = get_password_hash(new_pwd)
    invalidate_user_tokens(db, a)
    a.updated_at = datetime.now()
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="agent_password_reset", resource_type="agent",
                     resource_id=str(agent_id), detail="Agent password reset",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Password updated"}


@router.post("/{agent_id}/change-password")
@requires_role("admin")
async def change_agent_password(request: Request, agent_id: int, body: AgentResetPassword, otp_code: str = "",
                                db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return await reset_agent_password(request, agent_id, body, otp_code, db, current_user)


@router.post("/{agent_id}/assign-channels")
@requires_role("admin")
async def assign_agent_channels(request: Request, agent_id: int, payload: AssignChannelsRequest, otp_code: str = "",
                                db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "agents", otp_code)
    a = db.query(Agent).filter(Agent.id == int(agent_id)).first()
    if not a:
        raise HTTPException(404, "Agent not found")
    target_ids = list(payload.channel_ids or [])
    db.query(TrafficChannel).filter(TrafficChannel.agent_id == a.id).update(
        {TrafficChannel.agent_id: None}, synchronize_session=False)
    updated = 0
    if target_ids:
        updated = db.query(TrafficChannel).filter(TrafficChannel.id.in_(target_ids)).update(
            {TrafficChannel.agent_id: a.id}, synchronize_session=False) or 0
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="agent_assign_channels", resource_type="agent",
                     resource_id=str(agent_id), detail=f"Assigned {updated} channels",
                     ip_address=request.client.host if request.client else None)
    return {"assigned": int(updated), "channel_ids": target_ids}


@router.delete("/{agent_id}")
@requires_role("admin")
async def delete_agent(request: Request, agent_id: int, otp_code: str = "",
                       db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "agents", otp_code)
    a = db.query(Agent).filter(Agent.id == int(agent_id)).first()
    if not a:
        raise HTTPException(404, "Agent not found")
    uname = a.username
    db.query(Device).filter(Device.agent_id == a.id).update({Device.agent_id: None}, synchronize_session=False)
    db.query(TrafficChannel).filter(TrafficChannel.agent_id == a.id).update({TrafficChannel.agent_id: None}, synchronize_session=False)
    db.query(LandingTemplate).filter(LandingTemplate.agent_id == a.id).update({LandingTemplate.agent_id: None}, synchronize_session=False)
    db.query(DeviceGroup).filter(DeviceGroup.agent_id == a.id).update({DeviceGroup.agent_id: None}, synchronize_session=False)
    db.delete(a)
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="agent_delete", resource_type="agent",
                     resource_id=str(agent_id), detail=f"Deleted agent {uname}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Agent deleted"}


@router.post("/{agent_id}/assign")
@requires_role("admin")
async def assign_data(request: Request, agent_id: int, payload: AssignDataRequest, otp_code: str = "",
                      db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "agents", otp_code)
    a = db.query(Agent).filter(Agent.id == int(agent_id)).first()
    if not a:
        raise HTTPException(404, "Agent not found")
    t = (payload.type or "").lower()
    ids = list(payload.ids or [])
    if not ids:
        return {"assigned": 0}
    target_aid = a.id
    updated = 0
    if t == "device":
        updated = db.query(Device).filter(Device.id.in_(ids)).update({Device.agent_id: target_aid}, synchronize_session=False) or 0
    elif t == "channel":
        updated = db.query(TrafficChannel).filter(TrafficChannel.id.in_(ids)).update({TrafficChannel.agent_id: target_aid}, synchronize_session=False) or 0
    elif t == "template":
        updated = db.query(LandingTemplate).filter(LandingTemplate.id.in_(ids)).update({LandingTemplate.agent_id: target_aid}, synchronize_session=False) or 0
    elif t == "group":
        updated = db.query(DeviceGroup).filter(DeviceGroup.id.in_(ids)).update({DeviceGroup.agent_id: target_aid}, synchronize_session=False) or 0
    else:
        raise HTTPException(400, "Unknown assignment type, allowed: device | channel | template | group")
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="agent_assign_data", resource_type="agent",
                     resource_id=str(agent_id), detail=f"Assigned {updated} {t} items",
                     ip_address=request.client.host if request.client else None)
    return {"assigned": int(updated), "type": t}
