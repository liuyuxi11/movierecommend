from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from app import auth
from app.auth import get_current_user
from app.models import User
from app.schemas import UserChangePassword, UserCreate, UserLogin, UserUpdate

router = APIRouter()

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


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    if await _identity_conflict(
        username=user.username,
        phone=user.phone,
        email=str(user.email),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="昵称、手机号或邮箱已被注册",
        )

    try:
        new_user = await User.create(
            username=user.username,
            password=auth.get_password_hash(user.password),
            phone=user.phone,
            email=str(user.email),
            avatar=user.avatar,
        )
    except IntegrityError as exc:
        # Database unique indexes also protect registrations racing each other.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="昵称、手机号或邮箱已被注册",
        ) from exc

    return {"code": 201, "msg": "注册成功", "userid": new_user.userid}


@router.post("/login")
async def login(user: UserLogin):
    account = user.account.strip()
    db_user = await User.filter(
        (
            Q(username__iexact=account)
            | Q(phone=account)
            | Q(email__iexact=account)
        ),
        deleted_at=None,
        status="active",
    ).first()

    if not db_user or not auth.verify_password(user.password, db_user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth.create_access_token(
        data={"sub": str(db_user.userid), "username": db_user.username}
    )
    return {
        "code": 200,
        "msg": "登录成功",
        "access_token": token,
        "token_type": "bearer",
        "userid": db_user.userid,
    }


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
            detail="请至少提供一个需要修改的字段",
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
            detail="昵称、手机号或邮箱已被其他用户使用",
        )

    current_user.update_from_dict(update_data)
    try:
        await current_user.save()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="昵称、手机号或邮箱已被其他用户使用",
        ) from exc

    return {"code": 200, "msg": "资料修改成功"}

@router.put("/me/password")
async def change_password(
    data: UserChangePassword,
    current_user: User = Depends(get_current_user),
):
    if not auth.verify_password(data.old_password, current_user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )

    current_user.password = auth.get_password_hash(data.new_password)
    await current_user.save()
    return {"code": 200, "msg": "密码修改成功"}
