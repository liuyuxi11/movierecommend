import os
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
from app.models import User

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be configured in the environment")
ALGORITHM = "HS256"

# 告诉 FastAPI 登录接口在哪
# 假设你的登录路由是 /api/auth/login，请根据实际情况调整
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=2)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭证，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 1. 解码 Token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        raw_user_id = payload.get("sub")
        if raw_user_id is None:
            raise credentials_exception
        user_id = int(raw_user_id)
    except (JWTError, TypeError, ValueError):
        raise credentials_exception
        
    # Reject disabled and soft-deleted accounts even when their token has not expired.
    user = await User.get_or_none(userid=user_id, deleted_at=None, status="active")
    if user is None:
        raise credentials_exception
        
    return user
