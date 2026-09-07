from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime

from ...database import get_db, LandingTemplate
from ...agent_auth import get_current_agent, Agent

router = APIRouter(prefix="/api/agent/templates", tags=["agent-templates"], redirect_slashes=False)


@router.get("")
async def agent_templates_list(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)
):
    q = db.query(LandingTemplate).filter((LandingTemplate.agent_id == current_agent.id) | (LandingTemplate.agent_id.is_(None)))
    total = q.count()
    rows = q.order_by(desc(LandingTemplate.id)).offset(skip).limit(limit).all()
    items = []
    for t in rows:
        d = {col.name: getattr(t, col.name) for col in t.__table__.columns}
        for k in ("created_at", "updated_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        items.append(d)
    return {"total": total, "items": items}
