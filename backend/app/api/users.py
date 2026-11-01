from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

from app import auth
from app.auth import get_current_user
from app.avatar_storage import save_avatar
from app.email_service import send_password_reset_code, smtp_configured
from app.models import AdminUser, User
from app.schemas import (
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    UserChangePassword,
    UserCreate,
    UserLogin,
    UserUpdate,
)

router = APIRouter()
_RESET_CODE_TTL = timedelta(minutes=10)
_RESET_CODE_COOLDOWN = timedelta(seconds=60)
_RESET_MAX_ATTEMPTS = 5
_reset_codes: dict[str, dict[str, object]] = {}


async def _identity_conflict(
    *,
    username: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    exclude_userid: Optional[int] = None,
) -> bool:
    conditions = []
    if username is not None:
        conditions.append(Q(username__iexact=username))
    if phone is not None:
        conditions.append(Q(phone=phone))
    if email is not None:
        conditions.append(Q(email__iexact=email))
    if not conditions:
        return False

    identity_filter = conditions[0]
    for condition in conditions[1:]:
        identity_filter |= condition
    users = User.filter(identity_filter, deleted_at=None)
    if exclude_userid is not None:
        users = users.exclude(userid=exclude_userid)
    return await users.exists()


def _validated_user(payload: object) -> UserCreate:
    try:
        return UserCreate.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc


async def _create_user(user: UserCreate, avatar_url: Optional[str] = None) -> User:
    if await _identity_conflict(username=user.username, phone=user.phone, email=str(user.email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="昵称、手机号或邮箱已被注册")
    try:
        return await User.create(
            username=user.username,
            password=auth.get_password_hash(user.password),
            phone=user.phone,
            email=str(user.email),
            avatar=avatar_url if avatar_url is not None else user.avatar,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="昵称、手机号或邮箱已被注册") from exc


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    """JSON registration endpoint; FastAPI exposes UserCreate in Swagger."""
    new_user = await _create_user(user)
    return {"code": 201, "msg": "注册成功", "userid": new_user.userid}


@router.post("/register-with-avatar", status_code=status.HTTP_201_CREATED)
async def register_with_avatar(
    request: Request,
    username: str = Form(..., min_length=2, max_length=50),
    password: str = Form(..., min_length=8, max_length=255),
    confirm_password: str = Form(..., min_length=8, max_length=255),
    email: str = Form(..., max_length=254),
    phone: str = Form(..., min_length=1, max_length=32),
    avatar: Optional[UploadFile] = File(default=None),
):
    """Multipart registration endpoint for an uploaded avatar."""
    try:
        user = UserCreate.model_validate({
            "username": username,
            "password": password,
            "confirm_password": confirm_password,
            "email": email,
            "phone": phone,
        })
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    avatar_url = None
    if avatar is not None and avatar.filename:
        avatar_path = await save_avatar(avatar)
        avatar_url = f"{str(request.base_url).rstrip('/')}{avatar_path}"
    new_user = await _create_user(user, avatar_url=avatar_url)
    return {"code": 201, "msg": "注册成功", "userid": new_user.userid}


@router.post("/register-legacy", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def register_legacy(request: Request):
    """Register from JSON or multipart form data with an optional avatar file."""
    content_type = (request.headers.get("content-type") or "").lower()
    avatar_upload = None

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        payload = {
            "username": form.get("username"),
            "password": form.get("password"),
            "confirm_password": form.get("confirm_password"),
            "email": form.get("email"),
            "phone": form.get("phone"),
        }
        avatar = form.get("avatar")
        if isinstance(avatar, UploadFile) or (
            hasattr(avatar, "filename") and hasattr(avatar, "read")
        ):
            if avatar.filename:
                avatar_upload = avatar
        elif isinstance(avatar, str) and avatar.strip():
            payload["avatar"] = avatar.strip()
    else:
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Request body must be JSON or multipart/form-data",
            ) from exc

    user = _validated_user(payload)

    if await _identity_conflict(
        username=user.username,
        phone=user.phone,
        email=str(user.email),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="\u6635\u79f0\u3001\u624b\u673a\u53f7\u6216\u90ae\u7bb1\u5df2\u88ab\u6ce8\u518c",
        )

    if avatar_upload is not None:
        avatar_path = await save_avatar(avatar_upload)
        user.avatar = f"{str(request.base_url).rstrip('/')}{avatar_path}"

    try:
        new_user = await User.create(
            username=user.username,
            password=auth.get_password_hash(user.password),
            phone=user.phone,
            email=str(user.email),
            avatar=user.avatar,
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="\u6635\u79f0\u3001\u624b\u673a\u53f7\u6216\u90ae\u7bb1\u5df2\u88ab\u6ce8\u518c",
        ) from exc

    return {"code": 201, "msg": "\u6ce8\u518c\u6210\u529f", "userid": new_user.userid}


@router.post("/forgot-password/request")
async def request_password_reset(data: PasswordResetRequest):
    """Send a short-lived password reset code through configured SMTP."""
    if not smtp_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMTP \u90ae\u7bb1\u670d\u52a1\u5c1a\u672a\u914d\u7f6e",
        )

    email = str(data.email).lower()
    user = await User.filter(
        email__iexact=email, deleted_at=None, status="active"
    ).first()
    now = datetime.now(timezone.utc)
    previous = _reset_codes.get(email)
    if previous and now - previous["sent_at"] < _RESET_CODE_COOLDOWN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="\u9a8c\u8bc1\u7801\u53d1\u9001\u8fc7\u4e8e\u9891\u7e41\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5",
        )

    if user is None:
        return {"code": 200, "msg": "\u5982\u679c\u90ae\u7bb1\u5df2\u6ce8\u518c\uff0c\u9a8c\u8bc1\u7801\u5c06\u53d1\u9001\u5230\u8be5\u90ae\u7bb1"}

    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        await send_password_reset_code(email, code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="\u9a8c\u8bc1\u7801\u90ae\u4ef6\u53d1\u9001\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5 SMTP \u914d\u7f6e",
        ) from exc

    _reset_codes[email] = {
        "code_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "expires_at": now + _RESET_CODE_TTL,
        "sent_at": now,
        "attempts": 0,
    }
    return {"code": 200, "msg": "\u9a8c\u8bc1\u7801\u5df2\u53d1\u9001\uff0c\u8bf7\u67e5\u6536\u90ae\u7bb1"}


@router.post("/forgot-password/confirm")
async def confirm_password_reset(data: PasswordResetConfirm):
    email = str(data.email).lower()
    record = _reset_codes.get(email)
    now = datetime.now(timezone.utc)
    if not record or now >= record["expires_at"]:
        _reset_codes.pop(email, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u9a8c\u8bc1\u7801\u65e0\u6548\u6216\u5df2\u8fc7\u671f")
    if record["attempts"] >= _RESET_MAX_ATTEMPTS:
        _reset_codes.pop(email, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u9a8c\u8bc1\u7801\u5c1d\u8bd5\u6b21\u6570\u8fc7\u591a")

    record["attempts"] += 1
    code_hash = hashlib.sha256(data.code.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(code_hash, record["code_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u9a8c\u8bc1\u7801\u9519\u8bef")

    user = await User.filter(
        email__iexact=email, deleted_at=None, status="active"
    ).first()
    if user is None:
        _reset_codes.pop(email, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u9a8c\u8bc1\u7801\u65e0\u6548\u6216\u5df2\u8fc7\u671f")

    user.password = auth.get_password_hash(data.new_password)
    user.token_version += 1
    await user.save(update_fields=["password", "token_version", "updated_at"])
    _reset_codes.pop(email, None)
    return {"code": 200, "msg": "\u5bc6\u7801\u91cd\u7f6e\u6210\u529f"}


@router.post("/login")
async def login(user: UserLogin):
    account = user.account.strip()
    db_user = await User.filter(
        Q(username__iexact=account)
        | Q(phone=account)
        | Q(email__iexact=account),
        deleted_at=None,
        status="active",
    ).first()

    if not db_user or not auth.verify_password(user.password, db_user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="\u8d26\u53f7\u6216\u5bc6\u7801\u9519\u8bef",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = auth.create_token_pair(
        {"sub": str(db_user.userid), "username": db_user.username}, auth.get_user_token_version(db_user)
    )
    return {
        "code": 200,
        "msg": "\u767b\u5f55\u6210\u529f",
        **tokens,
        "userid": db_user.userid,
    }


@router.post("/token", include_in_schema=False)
async def oauth_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 form endpoint used by Swagger's Authorize dialog."""
    account = form_data.username.strip()
    db_user = await User.filter(
        Q(username__iexact=account)
        | Q(phone=account)
        | Q(email__iexact=account),
        deleted_at=None,
        status="active",
    ).first()
    if db_user and auth.verify_password(form_data.password, db_user.password):
        return auth.create_token_pair(
            {"sub": str(db_user.userid), "username": db_user.username},
            auth.get_user_token_version(db_user),
        )

    db_admin = await AdminUser.filter(
        username__iexact=account,
        deleted_at=None,
        status="active",
    ).first()
    if db_admin and auth.verify_password(form_data.password, db_admin.password):
        return auth.create_token_pair(
            {"admin_sub": str(db_admin.adminid), "role": db_admin.role},
            auth.get_admin_token_version(db_admin),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="账号或密码错误",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/me")
async def get_user_info(current_user: User = Depends(get_current_user)):
    return {
        "code": 200,
        "data": {
            "userid": current_user.userid,
            "username": current_user.username,
            "email": current_user.email,
            "phone": current_user.phone,
            "avatar": current_user.avatar,
        },
    }


@router.put("/me")
async def update_user_info(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
):
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="\u8bf7\u81f3\u5c11\u63d0\u4f9b\u4e00\u4e2a\u9700\u8981\u4fee\u6539\u7684\u5b57\u6bb5",
        )

    if await _identity_conflict(
        username=update_data.get("username"),
        phone=update_data.get("phone"),
        email=(
            str(update_data["email"])
            if update_data.get("email") is not None
            else None
        ),
        exclude_userid=current_user.userid,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="\u6635\u79f0\u3001\u624b\u673a\u53f7\u6216\u90ae\u7bb1\u5df2\u88ab\u5176\u4ed6\u7528\u6237\u4f7f\u7528",
        )

    current_user.update_from_dict(update_data)
    try:
        await current_user.save()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="\u6635\u79f0\u3001\u624b\u673a\u53f7\u6216\u90ae\u7bb1\u5df2\u88ab\u5176\u4ed6\u7528\u6237\u4f7f\u7528",
        ) from exc

    return {"code": 200, "msg": "\u8d44\u6599\u4fee\u6539\u6210\u529f"}


@router.put("/me/password")
async def change_password(
    data: UserChangePassword,
    current_user: User = Depends(get_current_user),
):
    if not auth.verify_password(data.old_password, current_user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="\u539f\u5bc6\u7801\u9519\u8bef",
        )

    current_user.password = auth.get_password_hash(data.new_password)
    current_user.token_version += 1
    await current_user.save(update_fields=["password", "token_version", "updated_at"])
    return {"code": 200, "msg": "\u5bc6\u7801\u4fee\u6539\u6210\u529f"}


@router.post("/refresh")
async def refresh_user_token(data: RefreshTokenRequest):
    tokens = await auth.refresh_token_pair(data.refresh_token)
    return {"code": 200, "data": tokens}


@router.post("/logout")
async def logout_user(current_user: User = Depends(get_current_user)):
    current_user.token_version += 1
    await current_user.save(update_fields=["token_version", "updated_at"])
    return {"code": 200, "msg": "已退出，请在客户端清除本地令牌；服务端凭证到期前仍可使用"}
