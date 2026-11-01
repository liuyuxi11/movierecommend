"""Manual administrator bootstrap endpoint.

This router is intentionally separate from the public user authentication
router. It is for controlled database seeding and is not used by the frontend.
"""

import hmac
import os

from dotenv import load_dotenv
from typing import Optional

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app import auth
from app.models import AdminOperationLog, AdminUser, CommentLikeEvent, User
from app.schemas import AdminAccountUpdate, AdminCreate, AdminLogin, RefreshTokenRequest, UserAdminUpdate

load_dotenv()

router = APIRouter()


@router.post("/login")
async def admin_login(data: AdminLogin):
    """Issue a JWT for an existing administrator (role in input is ignored)."""
    admin = await AdminUser.get_or_none(username=data.username, deleted_at=None, status="active")
    if admin is None or not auth.verify_password(data.password, admin.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员账号或密码错误")
    tokens = auth.create_token_pair(
        {"admin_sub": str(admin.adminid), "role": admin.role},
        auth.get_admin_token_version(admin),
    )
    return {"code": 200, "data": {**tokens, "role": admin.role}}


@router.post("/refresh")
async def refresh_admin_token(data: RefreshTokenRequest):
    tokens = await auth.refresh_token_pair(data.refresh_token, admin_account=True)
    return {"code": 200, "data": tokens}


@router.post("/logout")
async def logout_admin(admin: AdminUser = Depends(auth.get_current_admin)):
    admin.token_version += 1
    await admin.save(update_fields=["token_version", "updated_at"])
    return {"code": 200, "msg": "已退出，请在客户端清除本地令牌；服务端凭证到期前仍可使用"}


@router.get("/me")
async def admin_me(admin: AdminUser = Depends(auth.get_current_admin)):
    return {"code": 200, "data": {"adminid": admin.adminid, "username": admin.username, "role": admin.role}}


@router.get("/audit/logs")
async def list_operation_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None, max_length=100),
    target_type: Optional[str] = Query(None, max_length=50),
    admin: AdminUser = Depends(auth.get_current_admin),
):
    logs = AdminOperationLog.all()
    if action:
        logs = logs.filter(action=action)
    if target_type:
        logs = logs.filter(target_type=target_type)
    total = await logs.count()
    rows = await logs.order_by("-created_at", "-logid").offset((page - 1) * page_size).limit(page_size).values(
        "logid", "admin_id", "action", "target_type", "target_id", "detail", "created_at"
    )
    return {"code": 200, "data": {"items": rows, "total": total, "page": page, "page_size": page_size}}


@router.get("/audit/like-events")
async def list_like_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    event_action: Optional[str] = Query(None, alias="action"),
    admin: AdminUser = Depends(auth.get_current_admin),
):
    events = CommentLikeEvent.all()
    if event_action:
        events = events.filter(action=event_action)
    total = await events.count()
    rows = await events.order_by("-created_at", "-eventid").offset((page - 1) * page_size).limit(page_size).values(
        "eventid", "user_id", "comment_id", "action", "created_at"
    )
    return {"code": 200, "data": {"items": rows, "total": total, "page": page, "page_size": page_size}}


async def _log(admin: AdminUser, action: str, target_type: str, target_id, detail=None):
    await AdminOperationLog.create(
        admin=admin, action=action, target_type=target_type,
        target_id=str(target_id), detail=detail,
    )


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_status: Optional[str] = Query(None, alias="status"),
    admin: AdminUser = Depends(auth.require_superadmin),
):
    users = User.all()
    if user_status in {"active", "disabled"}:
        users = users.filter(status=user_status)
    total = await users.count()
    rows = await users.order_by("-created_at", "-userid").offset((page - 1) * page_size).limit(page_size).values(
        "userid", "username", "phone", "email", "avatar", "status", "created_at", "updated_at", "deleted_at"
    )
    return {"code": 200, "data": {"items": rows, "total": total, "page": page, "page_size": page_size}}


@router.put("/users/{userid}")
async def update_user_status(userid: int, data: UserAdminUpdate, admin: AdminUser = Depends(auth.require_superadmin)):
    user = await User.get_or_none(userid=userid, deleted_at=None)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在或已删除")
    user.status = data.status
    user.token_version += 1
    await user.save(update_fields=["status", "token_version", "updated_at"])
    await _log(admin, "user.status_update", "user", userid, {"status": data.status})
    return {"code": 200, "msg": "用户状态已更新", "data": {"userid": userid, "status": user.status}}


@router.delete("/users/{userid}")
async def delete_user(userid: int, admin: AdminUser = Depends(auth.require_superadmin)):
    user = await User.get_or_none(userid=userid, deleted_at=None)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在或已删除")
    user.deleted_at = datetime.now(timezone.utc)
    user.token_version += 1
    await user.save(update_fields=["deleted_at", "token_version", "updated_at"])
    await _log(admin, "user.delete", "user", userid)
    return {"code": 200, "msg": "用户已软删除"}


@router.get("/accounts")
async def list_admin_accounts(admin: AdminUser = Depends(auth.require_superadmin)):
    rows = await AdminUser.all().order_by("-created_at").values(
        "adminid", "username", "role", "status", "created_at", "updated_at", "deleted_at"
    )
    return {"code": 200, "data": rows}


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_admin_account(data: AdminCreate, admin: AdminUser = Depends(auth.require_superadmin)):
    existing = await AdminUser.filter(username__iexact=data.username).exists()
    if existing:
        raise HTTPException(status_code=409, detail="管理员账号已存在")
    try:
        created = await AdminUser.create(
            username=data.username, password=auth.get_password_hash(data.password),
            role=data.role, status="active",
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="管理员账号已存在") from exc
    await _log(admin, "admin.create", "admin", created.adminid, {"role": created.role})
    return {"code": 201, "data": {"adminid": created.adminid, "username": created.username, "role": created.role, "status": created.status}}


@router.put("/accounts/{adminid}")
async def update_admin_account(adminid: int, data: AdminAccountUpdate, admin: AdminUser = Depends(auth.require_superadmin)):
    target = await AdminUser.get_or_none(adminid=adminid, deleted_at=None)
    if target is None:
        raise HTTPException(status_code=404, detail="管理员不存在或已删除")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="至少提供 role 或 status")
    if target.adminid == admin.adminid and changes.get("status") == "disabled":
        raise HTTPException(status_code=400, detail="不能禁用当前登录的管理员")
    for key, value in changes.items():
        setattr(target, key, value)
    if "role" in changes or "status" in changes:
        target.token_version += 1
    await target.save(update_fields=[*changes.keys(), "token_version", "updated_at"])
    await _log(admin, "admin.update", "admin", adminid, changes)
    return {"code": 200, "msg": "管理员账号已更新"}


@router.delete("/accounts/{adminid}")
async def delete_admin_account(adminid: int, admin: AdminUser = Depends(auth.require_superadmin)):
    target = await AdminUser.get_or_none(adminid=adminid, deleted_at=None)
    if target is None:
        raise HTTPException(status_code=404, detail="管理员不存在或已删除")
    if target.adminid == admin.adminid:
        raise HTTPException(status_code=400, detail="不能删除当前登录的管理员")
    target.deleted_at = datetime.now(timezone.utc)
    target.token_version += 1
    await target.save(update_fields=["deleted_at", "token_version", "updated_at"])
    await _log(admin, "admin.delete", "admin", adminid)
    return {"code": 200, "msg": "管理员已软删除"}


def _require_bootstrap_token(token: Optional[str]) -> None:
    expected = os.getenv("ADMIN_BOOTSTRAP_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_BOOTSTRAP_TOKEN 尚未配置",
        )
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理员注入凭证无效",
        )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_admin(
    data: AdminCreate,
    x_admin_bootstrap_token: Optional[str] = Header(default=None),
):
    """Create a normal administrator or super administrator for DB seeding."""
    _require_bootstrap_token(x_admin_bootstrap_token)

    existing = await AdminUser.filter(username__iexact=data.username).exists()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="管理员账号已存在",
        )

    try:
        admin = await AdminUser.create(
            username=data.username,
            password=auth.get_password_hash(data.password),
            role=data.role,
            status="active",
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="管理员账号已存在",
        ) from exc

    return {
        "code": 201,
        "msg": "管理员创建成功",
        "data": {
            "adminid": admin.adminid,
            "username": admin.username,
            "role": admin.role,
            "status": admin.status,
        },
    }
