from fastapi import APIRouter, Depends

from ...agent_auth import get_current_agent, Agent

router = APIRouter(prefix="/api/agent/profile", tags=["agent-profile"], redirect_slashes=False)


@router.get("")
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
