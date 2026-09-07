from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from datetime import datetime
from typing import Optional

from ..database import get_db, AuditLog, Agent as AgentModel
from ..auth import get_current_user
from ._helpers import _resolve_agent_scope

router = APIRouter(prefix="/api/audit", tags=["audit"], redirect_slashes=False)


def _apply_audit_agent_filter(query, db, user):
    scope, aid = _resolve_agent_scope(db, user)
    if scope == "admin":
        return query
    username = getattr(user, "username", None)
    if username:
        query = query.filter(AuditLog.username == username)
    return query


@router.get("")
async def list_audit_logs(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    page: Optional[int] = None, page_size: Optional[int] = None,
    username: Optional[str] = None, action: Optional[str] = None,
    resource_type: Optional[str] = None, resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None, ip: Optional[str] = None,
    search: Optional[str] = None, q: Optional[str] = None,
    start_time: Optional[str] = None, end_time: Optional[str] = None,
    dateRange: Optional[str] = None,
    sort: Optional[str] = "timestamp", order: Optional[str] = "desc",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    if page and page_size and skip == 0:
        skip = (page - 1) * page_size
        limit = page_size
    use_resource = resource_type or resource
    use_ip = ip_address or ip
    use_search = search or q
    q = db.query(AuditLog)
    q = _apply_audit_agent_filter(q, db, current_user)
    if username: q = q.filter(AuditLog.username.contains(username))
    if action: q = q.filter(AuditLog.action == action)
    if use_resource: q = q.filter(AuditLog.resource_type == use_resource)
    if resource_id: q = q.filter(AuditLog.resource_id.contains(resource_id))
    if use_ip: q = q.filter(AuditLog.ip_address.contains(use_ip))
    if use_search and use_search.strip():
        kw = f"%{use_search.strip()}%"
        q = q.filter(or_(AuditLog.detail.like(kw), AuditLog.username.like(kw), AuditLog.action.like(kw)))
    def _p(s):
        if not s: return None
        try:
            if len(s) == 10: return datetime.strptime(s, "%Y-%m-%d")
            return datetime.fromisoformat(s.replace("Z", "+00:00").replace("+00:00", ""))
        except Exception:
            return None
    fs = _p(start_time)
    fe = _p(end_time)
    if fs: q = q.filter(AuditLog.timestamp >= fs)
    if fe: q = q.filter(AuditLog.timestamp <= fe)
    total = q.count()
    order_func = desc if (order or "desc").lower() != "asc" else None
    col = {"timestamp": AuditLog.timestamp, "id": AuditLog.id}.get((sort or "timestamp").lower(), AuditLog.timestamp)
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
        d["role"] = d.get("username") == "admin" and "admin" or "operator"
        d["detail"] = d.get("detail") or ""
        items.append(d)
    return {"total": total, "items": items, "skip": skip, "limit": limit}


@router.get("/actions")
async def audit_actions(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    from sqlalchemy import distinct
    rows = db.query(distinct(AuditLog.action)).all()
    actions = [r[0] for r in rows if r[0]]
    return {"items": actions}
