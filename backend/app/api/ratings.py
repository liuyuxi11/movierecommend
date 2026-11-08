from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from tortoise.functions import Avg, Count
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction
from app.auth import get_current_user
from app.models import MovieInfo, PersonalRating, User
from app.schemas import RatingSubmit


router = APIRouter()

# Domain name used by the API layer.  The existing database/model is still
# `personalratings`, so this alias does not require a schema change.
UserRating = PersonalRating


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

    try:
        async with in_transaction() as connection:
            # Lock the account row so concurrent rating batches for the same
            # user cannot both observe a missing (user_id, movie_id) row and
            # race to insert it.
            locked_user = await (
                User.filter(userid=current_user.userid)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if locked_user is None:
                raise HTTPException(status_code=401, detail="用户不存在或已失效")

            existing = await (
                UserRating.filter(
                    user_id=current_user.userid,
                    movie_id__in=data.movieids,
                )
                .using_db(connection)
                .all()
            )
            existing_by_movie = {item.movie_id: item for item in existing}
            to_create = []

            for movie_id, score in zip(data.movieids, data.ratings):
                rating = existing_by_movie.get(movie_id)
                if rating is None:
                    to_create.append(
                        UserRating(
                            user_id=current_user.userid,
                            movie_id=movie_id,
                            rating=score,
                            rated_at=now_utc,
                            timestamp=timestamp,
                        )
                    )
                else:
                    rating.rating = score
                    rating.rated_at = now_utc
                    rating.timestamp = timestamp

            if existing:
                await UserRating.bulk_update(
                    existing,
                    fields=["rating", "rated_at", "timestamp"],
                    using_db=connection,
                )
            if to_create:
                await UserRating.bulk_create(to_create, using_db=connection)

            # One grouped query calculates all changed movie aggregates, then
            # one bulk update writes the denormalized movie statistics.
            aggregates = await (
                UserRating.filter(movie_id__in=data.movieids)
                .using_db(connection)
                .annotate(average=Avg("rating"), count=Count("rating"))
                .group_by("movie_id")
                .values("movie_id", "average", "count")
            )
            aggregate_by_movie = {row["movie_id"]: row for row in aggregates}
            movies = await (
                MovieInfo.filter(movieid__in=data.movieids)
                .using_db(connection)
                .all()
            )
            for movie in movies:
                aggregate = aggregate_by_movie.get(movie.movieid)
                if aggregate:
                    movie.averating = aggregate["average"]
                    movie.numrating = aggregate["count"]
            if movies:
                await MovieInfo.bulk_update(
                    movies,
                    fields=["averating", "numrating"],
                    using_db=connection,
                )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="评分提交发生并发冲突，请重试",
        ) from exc

    return {"code": 200, "msg": "评分提交成功", "count": len(data.movieids)}
