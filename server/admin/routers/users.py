from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from ..database import get_db, User, create_audit_log
from ..auth import get_current_user, get_password_hash, authenticate_user, invalidate_user_tokens, requires_role
from ..schemas import UserCreate, UserUpdate, UserResponse
from .settings import require_module_2fa
from ..utils.totp import verify_totp

router = APIRouter(prefix="/api/users", tags=["users"], redirect_slashes=False)


class ChangePasswordRequest(BaseModel):
    current_password: Optional[str] = None
    new_password: Optional[str] = None
    password: Optional[str] = None


class Reset2FARequest(BaseModel):
    otp_code: Optional[str] = None


@router.get("")
@requires_role("admin")
async def list_users(
    skip: int = 0, limit: int = 100,
    page: Optional[int] = None, page_size: Optional[int] = None,
    search: Optional[str] = None, q: Optional[str] = None,
    role: Optional[str] = None, sort: Optional[str] = "id", order: Optional[str] = "desc",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    if page and page_size and skip == 0:
        skip = (page - 1) * page_size
        limit = page_size
    use_search = search or q
    q = db.query(User)
    if use_search and use_search.strip():
        kw = f"%{use_search.strip()}%"
        q = q.filter(User.username.like(kw))
    if role:
        q = q.filter(User.role == role)
    total = q.count()
    order_func = desc if (order or "desc").lower() != "asc" else None
    col = {"id": User.id, "username": User.username, "created_at": User.created_at,
           "last_login": User.last_login, "role": User.role}.get((sort or "id").lower(), User.id)
    q = q.order_by(desc(col) if order_func else col.asc())
    rows = q.offset(skip).limit(limit).all()
    items = []
    for u in rows:
        twofa = bool(u.google_2fa_enabled)
        items.append({
            "id": u.id, "username": u.username, "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "google_2fa_enabled": twofa,
            "twofa_enabled": twofa,
            "last_ip": u.last_login_ip,
        })
    return {"total": total, "items": items, "skip": skip, "limit": limit}


@router.get("/{user_id}")
@requires_role("admin")
async def get_user(user_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    u = db.query(User).filter(User.id == int(user_id)).first()
    if not u:
        raise HTTPException(404, "User not found")
    twofa = bool(u.google_2fa_enabled)
    return {
        "id": u.id, "username": u.username, "role": u.role,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "google_2fa_enabled": twofa,
        "twofa_enabled": twofa,
        "last_ip": u.last_login_ip,
    }


@router.post("")
@requires_role("admin")
async def create_user(request: Request, payload: UserCreate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "users", otp_code)
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(400, "用户名已存在")
    if not payload.password or len(payload.password) < 6:
        raise HTTPException(400, "密码长度至少 6 位")
    u = User(
        username=payload.username,
        password=get_password_hash(payload.password),
        role=payload.role or "operator",
        created_at=datetime.now(),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="user_create", resource_type="user",
                     resource_id=str(u.id), detail=f"Created user {u.username} role={u.role}",
                     ip_address=request.client.host if request.client else None)
    return {
        "id": u.id, "username": u.username, "role": u.role,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.patch("/{user_id}")
@requires_role("admin")
async def update_user(request: Request, user_id: int, payload: UserUpdate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "users", otp_code)
    u = db.query(User).filter(User.id == int(user_id)).first()
    if not u:
        raise HTTPException(404, "User not found")
    if payload.username is not None and payload.username != u.username:
        if db.query(User).filter(User.username == payload.username, User.id != u.id).first():
            raise HTTPException(400, "用户名已存在")
        u.username = payload.username
    if payload.role is not None:
        u.role = payload.role
        invalidate_user_tokens(db, u)
    if payload.password is not None:
        if len(payload.password) < 6:
            raise HTTPException(400, "密码长度至少 6 位")
        u.password = get_password_hash(payload.password)
        invalidate_user_tokens(db, u)
    db.commit()
    db.refresh(u)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="user_update", resource_type="user",
                     resource_id=str(u.id), detail=f"Updated user {u.username}",
                     ip_address=request.client.host if request.client else None)
    return {"id": u.id, "username": u.username, "role": u.role}


@router.delete("/{user_id}")
@requires_role("admin")
async def delete_user(request: Request, user_id: int, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "users", otp_code)
    u = db.query(User).filter(User.id == int(user_id)).first()
    if not u:
        raise HTTPException(404, "User not found")
    if u.username == current_user.username:
        raise HTTPException(400, "不能删除当前登录账号")
    uname = u.username
    db.delete(u)
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="user_delete", resource_type="user",
                     resource_id=str(user_id), detail=f"Deleted user {uname}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "User deleted"}


@router.post("/{user_id}/change-password")
@requires_role("admin")
async def admin_change_password(request: Request, user_id: int, body: ChangePasswordRequest, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "users", otp_code)
    u = db.query(User).filter(User.id == int(user_id)).first()
    if not u:
        raise HTTPException(404, "User not found")
    new_pwd = body.new_password or body.password
    if not new_pwd or len(new_pwd) < 6:
        raise HTTPException(400, "密码长度至少 6 位")
    u.password = get_password_hash(new_pwd)
    invalidate_user_tokens(db, u)
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="user_password_reset", resource_type="user",
                     resource_id=str(user_id), detail=f"Password reset for user id={user_id}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Password updated"}


@router.post("/{user_id}/reset-2fa")
@requires_role("admin")
async def admin_reset_2fa(request: Request, user_id: int, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "users", otp_code)
    u = db.query(User).filter(User.id == int(user_id)).first()
    if not u:
        raise HTTPException(404, "User not found")
    u.google_2fa_enabled = 0
    u.google_2fa_secret = None
    invalidate_user_tokens(db, u)
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="user_2fa_reset", resource_type="user",
                     resource_id=str(user_id), detail=f"2FA reset for user {u.username}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "2FA reset"}


@router.post("/me/change-password")
async def change_my_password(request: Request, body: ChangePasswordRequest, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "profile", otp_code)
    if not body.current_password or not authenticate_user(db, current_user.username, body.current_password):
        raise HTTPException(400, "当前密码错误")
    new_pwd = body.new_password or body.password
    if not new_pwd or len(new_pwd) < 6:
        raise HTTPException(400, "新密码长度至少 6 位")
    current_user.password = get_password_hash(new_pwd)
    invalidate_user_tokens(db, current_user)
    username = current_user.username
    create_audit_log(db, username=username, action="user_password_change", resource_type="user",
                     resource_id=str(current_user.id), detail="User changed own password",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Password updated, please login again"}


@router.post("/{user_id}/force-logout")
@requires_role("admin")
async def force_logout_user(request: Request, user_id: int, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "users", otp_code)
    u = db.query(User).filter(User.id == int(user_id)).first()
    if not u:
        raise HTTPException(404, "User not found")
    invalidate_user_tokens(db, u)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="user_force_logout", resource_type="user",
                     resource_id=str(user_id), detail=f"Forced logout user id={user_id}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "User tokens invalidated"}
