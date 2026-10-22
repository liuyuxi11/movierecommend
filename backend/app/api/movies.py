import random
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.models import Category, MovieCategory, MovieInfo


router = APIRouter()


@router.get("/random")
async def get_random_movies():
    movies = MovieInfo.filter(deleted_at=None)
    count = await movies.count()
    if count == 0:
        return {"code": 200, "data": []}

    offset = random.randint(0, max(0, count - 10))
    result = await movies.order_by("movieid").offset(offset).limit(10).values(
        "movieid",
        "moviename",
        "picture",
    )
    return {"code": 200, "data": result}


@router.get("")
async def list_movies(
    q: Optional[str] = Query(default=None, max_length=100),
    category_id: Optional[int] = Query(default=None, gt=0),
    sort_by: Literal["rating", "popularity", "release_time"] = "rating",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    movies = MovieInfo.filter(deleted_at=None)

    keyword = q.strip() if q else ""
    if keyword:
        movies = movies.filter(moviename__icontains=keyword)

    if category_id is not None:
        category_exists = await Category.filter(
            categoryid=category_id,
            deleted_at=None,
        ).exists()
        if not category_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="分类不存在或已删除",
            )
        movie_ids = await MovieCategory.filter(
            category_id=category_id,
        ).values_list("movie_id", flat=True)
        if not movie_ids:
            return {
                "code": 200,
                "data": {"items": [], "total": 0, "page": page, "page_size": page_size},
            }
        movies = movies.filter(movieid__in=movie_ids)

    sort_fields = {
        "rating": "averating",
        "popularity": "numrating",
        "release_time": "releasetime",
    }
    sort_field = sort_fields[sort_by]
    ordering = f"-{sort_field}" if order == "desc" else sort_field

    total = await movies.count()
    items = await (
        movies.order_by(ordering, "movieid")
        .offset((page - 1) * page_size)
        .limit(page_size)
        .values(
            "movieid",
            "moviename",
            "picture",
            "averating",
            "numrating",
            "releasetime",
        )
    )
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/{movieid}")
async def get_movie_detail(movieid: int):
    movie = await MovieInfo.filter(
        movieid=movieid,
        deleted_at=None,
    ).values(
        "movieid",
        "moviename",
        "releasetime",
        "director",
        "leadactors",
        "picture",
        "averating",
        "numrating",
        "description",
        "typelist",
    ).first()
    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="电影不存在或已删除",
        )
    return {"code": 200, "data": movie}
