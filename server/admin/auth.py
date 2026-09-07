from datetime import datetime, timedelta, timezone
from functools import wraps
import inspect
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request, Cookie, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db, User
from . import config

SECRET_KEY = config.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)
ADMIN_COOKIE_NAME = "ds_admin_token"


def _resolve_token(
    bearer_token: Optional[str],
    query_token: Optional[str],
    cookie_token: Optional[str],
) -> Optional[str]:
    # Priority: Bearer Authorization header > query ?token= > Cookie ds_admin_token
    if bearer_token:
        return bearer_token
    if query_token:
        return query_token
    if cookie_token:
        return cookie_token
    return None


def verify_password(plain_password, hashed_password):
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_user(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()


def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.password):
        return False
    return user


async def get_current_user(
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    token: Optional[str] = Query(default=None, alias="token", include_in_schema=False),
    ds_admin_token: Optional[str] = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    db: Session = Depends(get_db)
):
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    resolved = _resolve_token(bearer_token, token, ds_admin_token)
    if not resolved:
        raise cred_exc
    try:
        payload = jwt.decode(resolved, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") == "agent":
            raise cred_exc
        username: str = payload.get("sub")
        if username is None:
            raise cred_exc
        token_version = payload.get("ver", 0)
    except JWTError:
        raise cred_exc
    user = get_user(db, username=username)
    if user is None:
        raise cred_exc
    db_ver = getattr(user, "token_version", 0) or 0
    if int(token_version) != int(db_ver):
        raise cred_exc
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    return current_user


def requires_role(role: str):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if current_user.role != role and current_user.role != "admin":
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return await func(*args, current_user=current_user, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if current_user.role != role and current_user.role != "admin":
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return func(*args, current_user=current_user, **kwargs)

        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
    return decorator


def invalidate_user_tokens(db: Session, user: User):
    user.token_version = (getattr(user, "token_version", 0) or 0) + 1
    db.commit()


def get_or_create_admin(db: Session):
    existing = db.query(User).first()
    if existing is not None:
        return existing
    admin = User(
        username="admin",
        password=get_password_hash("admin123"),
        role="admin"
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin
