from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from tortoise.transactions import in_transaction
from app.auth import get_current_user
from app.models import MovieInfo, PersonalRating, User
from app.schemas import RatingSubmit


router = APIRouter()


@router.get("/me")
async def get_my_ratings(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    ratings = PersonalRating.filter(
        user_id=current_user.userid,
        movie__deleted_at=None,
    ).order_by("-rated_at", "-ratingid")
    total = await ratings.count()
    rows = await ratings.offset((page - 1) * page_size).limit(page_size).values(
        "ratingid",
        "movie_id",
        "rating",
        "rated_at",
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
            "ratingid": row["ratingid"],
            "movieid": row["movie_id"],
            "moviename": movies_by_id[row["movie_id"]]["moviename"],
            "picture": movies_by_id[row["movie_id"]]["picture"],
            "rating": row["rating"],
            "rated_at": row["rated_at"],
        }
        for row in rows
        if row["movie_id"] in movies_by_id
    ]
    return {
        "code": 200,
        "data": {"items": items, "total": total, "page": page, "page_size": page_size},
    }


@router.post("/submit")
async def submit_ratings(
    data: RatingSubmit,
    current_user: User = Depends(get_current_user),
):
    if data.userid is not None and data.userid != current_user.userid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能为其他用户提交评分",
        )

    active_movie_ids = set(
        await MovieInfo.filter(
            movieid__in=data.movieids,
            deleted_at=None,
        ).values_list("movieid", flat=True)
    )
    missing_movie_ids = sorted(set(data.movieids) - active_movie_ids)
    if missing_movie_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "电影不存在或已删除", "movieids": missing_movie_ids},
        )

    now_utc = datetime.now(timezone.utc)
    timestamp = str(int(now_utc.timestamp()))

    async with in_transaction() as connection:
        for movie_id, score in zip(data.movieids, data.ratings):
            rating = await (
                PersonalRating.filter(
                    user_id=current_user.userid,
                    movie_id=movie_id,
                )
                .using_db(connection)
                .first()
            )
            if rating is None:
                await PersonalRating.create(
                    user_id=current_user.userid,
                    movie_id=movie_id,
                    rating=score,
                    rated_at=now_utc,
                    timestamp=timestamp,
                    using_db=connection,
                )
            else:
                rating.rating = score
                rating.rated_at = now_utc
                rating.timestamp = timestamp
                await rating.save(using_db=connection)

    return {"code": 200, "msg": "评分提交成功", "count": len(data.movieids)}
