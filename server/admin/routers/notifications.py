import asyncio
import json
from fastapi import APIRouter, Depends, Query, Request, HTTPException, status, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime
from typing import Optional
from jose import JWTError, jwt

from ..database import get_db, Notification, create_notification, User, Device, Agent as AgentModel
from ..auth import get_current_user, SECRET_KEY, ALGORITHM
from ._helpers import _resolve_agent_scope

router = APIRouter(prefix="/api/notifications", tags=["notifications"], redirect_slashes=False)

_notification_queues: list = []
_db_session_factory = None
_main_event_loop = None


def register_main_loop(loop) -> None:
    global _main_event_loop
    _main_event_loop = loop


def _register_db_factory(factory):
    global _db_session_factory
    if callable(factory):
        _db_session_factory = factory


def _user_can_see_notification(user, notification: dict) -> bool:
    if user is None:
        return False
    role = getattr(user, "role", None) or ""
    if role == "admin":
        return True
    if role not in ("agent", "operator"):
        return True
    related_device_uuid = notification.get("related_device_uuid")
    if not related_device_uuid:
        return True
    if not _db_session_factory:
        return True
    try:
        from ..database import Device, Agent as AgentModel
        db = _db_session_factory()
        try:
            dev = db.query(Device).filter(Device.device_uuid == related_device_uuid).first()
            if not dev:
                return True
            if dev.agent_id is None:
                return True
            user_id = getattr(user, "id", None)
            if user_id and dev.agent_id == user_id:
                return True
            username = getattr(user, "username", None)
            if username:
                ag = db.query(AgentModel).filter(AgentModel.username == username).first()
                if ag and dev.agent_id == ag.id:
                    return True
            return False
        finally:
            db.close()
    except Exception:
        return True


def _apply_notification_agent_filter(query, db, user):
    scope, aid = _resolve_agent_scope(db, user)
    if scope == "admin" or aid is None:
        return query
    return query.outerjoin(Device, Notification.related_device_uuid == Device.device_uuid).filter(
        (Notification.related_device_uuid.is_(None)) | (Device.agent_id == aid)
    )


def _assert_owns_notification(db: Session, user, notif: Notification) -> None:
    if notif is None:
        return
    scope, aid = _resolve_agent_scope(db, user)
    if scope == "admin" or aid is None:
        return
    related_device_uuid = notif.related_device_uuid
    if not related_device_uuid:
        return
    dev = db.query(Device).filter(Device.device_uuid == related_device_uuid).first()
    if not dev or dev.agent_id is None:
        return
    if int(dev.agent_id) != int(aid):
        raise HTTPException(status_code=403, detail="无权限访问该通知")


def _broadcast_notification(notification: dict):
    dead_queues = []
    for entry in _notification_queues:
        try:
            if not isinstance(entry, dict):
                if hasattr(entry, "put_nowait"):
                    entry.put_nowait(notification)
                else:
                    dead_queues.append(entry)
                continue
            queue = entry.get("queue")
            user = entry.get("user")
            if user is not None and not _user_can_see_notification(user, notification):
                continue
            if queue and hasattr(queue, "put_nowait"):
                queue.put_nowait(notification)
            else:
                dead_queues.append(entry)
        except Exception:
            dead_queues.append(entry)
    for q in dead_queues:
        if q in _notification_queues:
            try:
                _notification_queues.remove(q)
            except ValueError:
                pass


async def _get_current_user_sse(
    request: Request,
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    raw = None
    if authorization and authorization.startswith("Bearer "):
        raw = authorization[7:]
    elif token:
        raw = token
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = jwt.decode(raw, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("")
async def get_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    query = db.query(Notification).order_by(desc(Notification.timestamp))
    query = _apply_notification_agent_filter(query, db, current_user)
    if unread_only:
        query = query.filter(Notification.is_read == 0)
    if category:
        query = query.filter(Notification.category == category)
    total = query.count()
    rows = query.offset(skip).limit(limit).all()
    unread_q = _apply_notification_agent_filter(db.query(func.count(Notification.id)), db, current_user)
    unread_count = unread_q.filter(Notification.is_read == 0).scalar()
    items = []
    for n in rows:
        ts_iso = n.timestamp.isoformat() if isinstance(n.timestamp, datetime) else n.timestamp
        read_bool = not (n.is_read == 0 or n.is_read is False)
        items.append({
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "content": n.message,
            "description": n.message,
            "category": n.category,
            "is_read": n.is_read,
            "read": read_bool,
            "related_device_uuid": n.related_device_uuid,
            "related_resource_type": n.related_resource_type,
            "related_resource_id": n.related_resource_id,
            "timestamp": ts_iso,
            "time": ts_iso,
            "created_at": ts_iso,
        })
    return {"total": total, "unread_count": unread_count, "items": items, "skip": skip, "limit": limit}


@router.get("/unread-count")
async def get_unread_count(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    unread_q = _apply_notification_agent_filter(db.query(func.count(Notification.id)), db, current_user)
    count = unread_q.filter(Notification.is_read == 0).scalar()
    return {"unread_count": count}


@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        return {"message": "Notification not found"}
    _assert_owns_notification(db, current_user, notif)
    notif.is_read = 1
    db.commit()
    return {"message": "Notification marked as read"}


@router.put("/read")
async def mark_all_read(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    q = _apply_notification_agent_filter(db.query(Notification), db, current_user)
    q.filter(Notification.is_read == 0).update({"is_read": 1}, synchronize_session=False)
    db.commit()
    return {"message": "All notifications marked as read"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    n = db.query(Notification).filter(Notification.id == int(notification_id)).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    _assert_owns_notification(db, current_user, n)
    db.delete(n)
    db.commit()
    return {"message": "Deleted", "id": notification_id}


@router.delete("")
async def clear_notifications(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    query = _apply_notification_agent_filter(db.query(Notification), db, current_user)
    if category:
        query = query.filter(Notification.category == category)
    deleted = query.delete(synchronize_session=False)
    db.commit()
    return {"message": f"Cleared {deleted} notifications"}


@router.head("/stream")
async def notification_stream_head(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user_sse)
):
    """HEAD 路由：仅用于前端 SSE 预检（返回响应头 + Content-Type），不注册长连接不消耗资源。"""
    from fastapi.responses import Response
    return Response(
        content=None,
        status_code=200,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/stream")
async def notification_stream(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user_sse)
):
    from ..database import SessionLocal
    _register_db_factory(SessionLocal)
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    entry = {"queue": queue, "user": current_user}
    _notification_queues.append(entry)

    async def event_generator():
        try:
            yield f"event: connected\ndata: {{\"message\": \"SSE connected\"}}\n\n"
            while True:
                try:
                    notification = await asyncio.wait_for(queue.get(), timeout=30.0)
                    data = json.dumps(notification, ensure_ascii=False, default=str)
                    yield f"event: notification\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: heartbeat\ndata: {{}}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if entry in _notification_queues:
                try:
                    _notification_queues.remove(entry)
                except ValueError:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def broadcast_notification_sync(db: Session, title: str, message: str, category: str = "info",
                                 related_device_uuid: str = None, related_resource_type: str = None,
                                 related_resource_id: str = None):
    try:
        create_notification(
            db, title, message, category,
            related_device_uuid, related_resource_type, related_resource_id
        )
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    notif_dict = {
        "id": None,
        "title": title,
        "message": message,
        "description": message,
        "category": category,
        "type": category,
        "related_device_uuid": related_device_uuid,
        "related_resource_type": related_resource_type,
        "related_resource_id": related_resource_id,
        "timestamp": datetime.now().isoformat(),
        "created_at": datetime.now().isoformat(),
        "read": False,
        "is_read": 0,
    }
    loop = None
    try:
        loop = _main_event_loop
    except Exception:
        loop = None
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except Exception:
            loop = None
    dispatched_via_loop = False
    if loop is not None and loop.is_running():
        try:
            same_thread = False
            try:
                running_loop = asyncio.get_running_loop()
                if running_loop is loop:
                    same_thread = True
            except RuntimeError:
                same_thread = False
            except Exception:
                same_thread = False
            if same_thread:
                _broadcast_notification(notif_dict)
                dispatched_via_loop = True
            else:
                loop.call_soon_threadsafe(_broadcast_notification, notif_dict)
                dispatched_via_loop = True
        except Exception:
            dispatched_via_loop = False
    if not dispatched_via_loop:
        try:
            _broadcast_notification(notif_dict)
        except Exception:
            pass
