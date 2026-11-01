import os
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
from app.models import AdminUser, User

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be configured in the environment")
ALGORITHM = "HS256"

# 告诉 FastAPI 登录接口在哪
# 假设你的登录路由是 /api/auth/login，请根据实际情况调整
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
optional_bearer = HTTPBearer(auto_error=False)

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + timedelta(minutes=15), "token_type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.now(timezone.utc) + timedelta(days=7), "token_type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_token_pair(subject: dict, token_version: int) -> dict:
    claims = {**subject, "ver": token_version}
    return {
        "access_token": create_access_token(claims),
        "refresh_token": create_refresh_token(claims),
        "token_type": "bearer",
        "expires_in": 900,
        "refresh_expires_in": 604800,
    }


def get_user_token_version(user: User) -> int:
    """Return the optional token version used by newer schemas.

    Older deployments do not have ``user.token_version``; those accounts use
    version 0 and are still invalidated by the active/soft-delete checks.
    """
    return int(getattr(user, "token_version", 0) or 0)


def get_admin_token_version(admin: AdminUser) -> int:
    """Support administrator tables created before token_version existed."""
    return int(getattr(admin, "token_version", 0) or 0)


async def refresh_token_pair(token: str, *, admin_account: bool = False) -> dict:
    invalid = HTTPException(status_code=401, detail="无效或过期的刷新凭证")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "refresh":
            raise invalid
        if admin_account:
            account_id = int(payload["admin_sub"])
            account = await AdminUser.get_or_none(adminid=account_id, deleted_at=None, status="active")
            subject = {"admin_sub": str(account_id), "role": account.role} if account else None
        else:
            account_id = int(payload["sub"])
            account = await User.get_or_none(userid=account_id, deleted_at=None, status="active")
            subject = {"sub": str(account_id), "username": account.username} if account else None
    except (JWTError, KeyError, TypeError, ValueError):
        raise invalid
    expected_version = (
        get_admin_token_version(account)
        if admin_account
        else get_user_token_version(account)
    )
    if account is None or payload.get("ver", 0) != expected_version:
        raise invalid
    return create_token_pair(subject, expected_version)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 1. 解码 Token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "access":
            raise credentials_exception
        raw_user_id = payload.get("sub")
        if raw_user_id is None:
            raise credentials_exception
        user_id = int(raw_user_id)
    except (JWTError, TypeError, ValueError):
        raise credentials_exception
        
    # Reject disabled and soft-deleted accounts even when their token has not expired.
    user = await User.get_or_none(userid=user_id, deleted_at=None, status="active")
    if user is None or payload.get("ver", 0) != get_user_token_version(user):
        raise credentials_exception
        
    return user


async def get_current_admin(token: str = Depends(oauth2_scheme)) -> AdminUser:
    """Resolve an active administrator from a JWT issued for an admin account."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的管理员认证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "access":
            raise credentials_exception
        raw_admin_id = payload.get("admin_sub")
        if raw_admin_id is None:
            raise credentials_exception
        admin_id = int(raw_admin_id)
    except (JWTError, TypeError, ValueError):
        raise credentials_exception

    admin = await AdminUser.get_or_none(adminid=admin_id, deleted_at=None, status="active")
    if admin is None or payload.get("ver", 0) != get_admin_token_version(admin):
        raise credentials_exception
    return admin


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
) -> Optional[User]:
    """Resolve a user when a bearer token is supplied; allow anonymous reads."""
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "access" or payload.get("sub") is None:
            raise ValueError("invalid access token")
        user_id = int(payload["sub"])
    except (JWTError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await User.get_or_none(userid=user_id, deleted_at=None, status="active")
    if user is None or payload.get("ver", 0) != get_user_token_version(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_superadmin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if admin.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限")
    return admin
