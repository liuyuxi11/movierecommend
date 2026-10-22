from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction
from app.auth import get_current_user
from app.models import MovieInfo, User, UserFavorite


router = APIRouter()


class FavoriteRequest(BaseModel):
    movieid: int = Field(gt=0)
    status: Literal["want_to_watch", "watched"]


@router.get("/me")
async def get_my_favorites(
    favorite_status: Optional[Literal["want_to_watch", "watched"]] = Query(
        default=None,
        alias="status",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    favorites = UserFavorite.filter(
        user_id=current_user.userid,
        deleted_at=None,
        movie__deleted_at=None,
    )
    if favorite_status is not None:
        favorites = favorites.filter(status=favorite_status)

    total = await favorites.count()
    rows = await favorites.order_by("-updated_at", "-id").offset(
        (page - 1) * page_size
    ).limit(page_size).values(
        "id",
        "movie_id",
        "status",
        "created_at",
        "updated_at",
    )
    if not rows:
        return {
            "code": 200,
            "data": {"items": [], "total": total, "page": page, "page_size": page_size},
        }

    movie_rows = await MovieInfo.filter(
        movieid__in=[row["movie_id"] for row in rows],
        deleted_at=None,
    ).values("movieid", "moviename", "picture")
    movies_by_id = {movie["movieid"]: movie for movie in movie_rows}
    items = [
        {
            "movieid": row["movie_id"],
            "moviename": movies_by_id[row["movie_id"]]["moviename"],
            "picture": movies_by_id[row["movie_id"]]["picture"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
        if row["movie_id"] in movies_by_id
    ]
    return {
        "code": 200,
        "data": {"items": items, "total": total, "page": page, "page_size": page_size},
    }


@router.post("/toggle")
async def toggle_favorite(
    data: FavoriteRequest,
    current_user: User = Depends(get_current_user),
):
    movie_exists = await MovieInfo.filter(
        movieid=data.movieid,
        deleted_at=None,
    ).exists()
    if not movie_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="电影不存在或已删除",
        )

    now_utc = datetime.now(timezone.utc)
    try:
        async with in_transaction() as connection:
            favorite = await (
                UserFavorite.filter(
                    user_id=current_user.userid,
                    movie_id=data.movieid,
                )
                .using_db(connection)
                .select_for_update()
                .first()
            )

            if favorite is None:
                await UserFavorite.create(
                    user_id=current_user.userid,
                    movie_id=data.movieid,
                    status=data.status,
                    created_at=now_utc,
                    updated_at=now_utc,
                    using_db=connection,
                )
                action = "add"
                message = "收藏成功"
            elif favorite.deleted_at is not None:
                favorite.deleted_at = None
                favorite.status = data.status
                favorite.updated_at = now_utc
                await favorite.save(using_db=connection)
                action = "add"
                message = "收藏成功"
            elif favorite.status == data.status:
                favorite.deleted_at = now_utc
                favorite.updated_at = now_utc
                await favorite.save(using_db=connection)
                action = "remove"
                message = "已取消收藏"
            else:
                favorite.status = data.status
                favorite.updated_at = now_utc
                await favorite.save(using_db=connection)
                action = "update"
                message = "收藏状态已更新"
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="收藏状态已被并发修改，请重试",
        ) from exc

    return {"code": 200, "msg": message, "action": action}
