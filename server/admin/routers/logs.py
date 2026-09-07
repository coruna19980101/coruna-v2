from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_
from datetime import datetime
from typing import Optional

from ..database import get_db, Log, Device
from ..auth import get_current_user
from ._helpers import _resolve_agent_scope

router = APIRouter(prefix="/api/logs", tags=["logs"], redirect_slashes=False)


def _apply_log_agent_filter(query, db, user):
    scope, aid = _resolve_agent_scope(db, user)
    if scope == "admin" or aid is None:
        return query
    return query.join(Device, Log.device_uuid == Device.device_uuid).filter(Device.agent_id == aid)


@router.get("")
async def list_logs(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    page: Optional[int] = None, page_size: Optional[int] = None,
    ip: Optional[str] = None, path: Optional[str] = None, log_type: Optional[str] = None,
    method: Optional[str] = None, status_code: Optional[int] = None,
    status: Optional[str] = None,
    device_uuid: Optional[str] = None, channel_id: Optional[int] = None, template_id: Optional[int] = None,
    start_time: Optional[str] = None, end_time: Optional[str] = None,
    search: Optional[str] = None, q: Optional[str] = None,
    sort: Optional[str] = "timestamp", order: Optional[str] = "desc",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    if page and page_size and skip == 0:
        skip = (page - 1) * page_size
        limit = page_size
    use_search = search or q
    q = db.query(Log)
    q = _apply_log_agent_filter(q, db, current_user)
    if ip: q = q.filter(Log.ip.contains(ip))
    if path: q = q.filter(Log.path.contains(path))
    if log_type: q = q.filter(Log.log_type == log_type)
    if method: q = q.filter(Log.method == method.upper())
    if status_code is not None:
        q = q.filter(Log.status_code == int(status_code))
    elif status and len(status) == 1 and status.isdigit():
        low = int(status) * 100
        high = low + 99
        q = q.filter(and_(Log.status_code >= low, Log.status_code <= high))
    if device_uuid: q = q.filter(Log.device_uuid == device_uuid)
    if channel_id is not None: q = q.filter(Log.channel_id == int(channel_id))
    if template_id is not None: q = q.filter(Log.template_id == int(template_id))
    if use_search and use_search.strip():
        kw = f"%{use_search.strip()}%"
        q = q.filter(or_(Log.path.like(kw), Log.user_agent.like(kw), Log.ip.like(kw)))
    def _p(s):
        if not s: return None
        try:
            if len(s) == 10: return datetime.strptime(s, "%Y-%m-%d")
            return datetime.fromisoformat(s.replace("Z", "+00:00").replace("+00:00", ""))
        except Exception:
            return None
    fs = _p(start_time)
    fe = _p(end_time)
    if fs: q = q.filter(Log.timestamp >= fs)
    if fe: q = q.filter(Log.timestamp <= fe)
    total = q.count()
    order_func = desc if (order or "desc").lower() != "asc" else None
    col = {"timestamp": Log.timestamp, "status_code": Log.status_code,
           "id": Log.id, "content_length": Log.content_length,
           }.get((sort or "timestamp").lower(), Log.timestamp)
    q = q.order_by(desc(col) if order_func else col.asc())
    rows = q.offset(skip).limit(limit).all()
    items = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        ts = d.get("timestamp")
        if isinstance(ts, datetime):
            ts_iso = ts.isoformat()
            d["timestamp"] = ts_iso
            d["time"] = ts_iso
            d["created_at"] = ts_iso
        d["status"] = d.get("status_code")
        d["size"] = d.get("content_length")
        d["bytes"] = d.get("content_length")
        d["ua"] = d.get("user_agent")
        items.append(d)
    return {"total": total, "items": items, "skip": skip, "limit": limit}


@router.get("/types")
async def log_types(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from sqlalchemy import distinct
    rows = db.query(distinct(Log.log_type)).all()
    types = [r[0] for r in rows if r[0]]
    return {"items": types}
