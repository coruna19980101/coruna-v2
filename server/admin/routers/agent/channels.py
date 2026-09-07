from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime
from typing import Optional

from ...database import get_db, TrafficChannel, Device
from ...agent_auth import get_current_agent, Agent

router = APIRouter(prefix="/api/agent/channels", tags=["agent-channels"], redirect_slashes=False)


@router.get("")
async def agent_channels_list(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)
):
    q = db.query(TrafficChannel).filter(TrafficChannel.agent_id == current_agent.id)
    total = q.count()
    rows = q.order_by(desc(TrafficChannel.id)).offset(skip).limit(limit).all()
    items = []
    for c in rows:
        d = {col.name: getattr(c, col.name) for col in c.__table__.columns}
        for k in ("created_at", "updated_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        d["device_count"] = int(db.query(func.count(Device.id)).filter(Device.channel_id == c.id).scalar() or 0)
        items.append(d)
    return {"total": total, "items": items}
