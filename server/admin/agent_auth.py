from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db, Agent
from . import config

SECRET_KEY = config.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")
agent_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/agent/auth/login", auto_error=False)


def agent_verify_password(plain_password, hashed_password):
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def agent_get_password_hash(password):
    return pwd_context.hash(password)


def create_agent_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_agent(db: Session, username: str):
    return db.query(Agent).filter(Agent.username == username).first()


def authenticate_agent(db: Session, username: str, password: str):
    agent = get_agent(db, username)
    if not agent:
        return False
    if not agent_verify_password(password, agent.password):
        return False
    if int(agent.enabled if agent.enabled is not None else 1) != 1:
        return False
    return agent


async def get_current_agent(token: str = Depends(agent_oauth2_scheme), db: Session = Depends(get_db)):
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate agent credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise cred_exc
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "agent":
            raise cred_exc
        username: str = payload.get("sub")
        if username is None:
            raise cred_exc
        token_version = payload.get("ver", 0)
    except JWTError:
        raise cred_exc
    agent = get_agent(db, username=username)
    if agent is None:
        raise cred_exc
    if int(agent.enabled if agent.enabled is not None else 1) != 1:
        raise cred_exc
    db_ver = getattr(agent, "token_version", 0) or 0
    if int(token_version) != int(db_ver):
        raise cred_exc
    return agent


def invalidate_agent_tokens(db: Session, agent: Agent):
    agent.token_version = (getattr(agent, "token_version", 0) or 0) + 1
    db.commit()
