import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent

if load_dotenv is not None:
    dotenv_path = BASE_DIR / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path)

_WEAK_KEYS = {
    "darksword_secret_key_change_me",
    "darksword_secret_key_2026_security_admin_panel",
    "",
    "change_me",
    "secret",
}
SECRET_KEY = os.getenv("SECRET_KEY", "")
if SECRET_KEY in _WEAK_KEYS:
    raise RuntimeError(
        "[SECURITY] SECRET_KEY 未配置或使用了已知弱默认值。\n"
        "请在 admin/.env 中设置随机强密钥，可用以下命令生成：\n"
        "  python -c \"import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))\""
    )
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

_CORS_STR = os.getenv("CORS_ORIGINS", "")
if _CORS_STR:
    CORS_ORIGINS = [o.strip() for o in _CORS_STR.split(",") if o.strip()]
else:
    CORS_ORIGINS = ["http://localhost:7070", "http://localhost:5173", "http://localhost:3000"]

RATE_LIMIT = os.getenv("RATE_LIMIT", "100/minute")
AUTH_RATE_LIMIT = os.getenv("AUTH_RATE_LIMIT", "5/minute")

DARKSWORD_PUBLIC_BASE = os.getenv("DARKSWORD_PUBLIC_BASE", "")
