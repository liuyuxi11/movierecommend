import random
from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction
from app import auth
from app.models import AdminOperationLog, AdminUser, Category, MovieCategory, MovieInfo
from app.redis_cache import cache_get, cache_set
from app.schemas import CategoryCreate, CategoryUpdate, MovieCreate, MovieUpdate


router = APIRouter()


async def _write_log(admin: AdminUser, action: str, target_type: str, target_id=None, detail=None, using_db=None):
    await AdminOperationLog.create(
        admin=admin, action=action, target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=jsonable_encoder(detail) if detail is not None else None,
        using_db=using_db,
    )


async def _set_movie_categories(movie: MovieInfo, category_ids: list[int], using_db=None) -> None:
    unique_ids = set(category_ids)
    if len(unique_ids) != len(category_ids) or any(category_id <= 0 for category_id in category_ids):
        raise HTTPException(status_code=422, detail="category_ids 必须为不重复的正整数")
    category_query = Category.filter(categoryid__in=unique_ids, deleted_at=None)
    if using_db is not None:
        category_query = category_query.using_db(using_db)
    categories = await category_query
    if len(categories) != len(unique_ids):
        raise HTTPException(status_code=404, detail="分类不存在或已删除")
    relation_query = MovieCategory.filter(movie_id=movie.movieid)
    if using_db is not None:
        relation_query = relation_query.using_db(using_db)
    await relation_query.delete()
    for category in categories:
        await MovieCategory.create(movie=movie, category=category, using_db=using_db)


@router.get("/categories")
async def list_categories():
    categories = await Category.filter(deleted_at=None).order_by("name").values("categoryid", "name")
    return {"code": 200, "data": categories}


@router.post("", status_code=201)
async def create_movie(data: MovieCreate, admin: AdminUser = Depends(auth.get_current_admin)):
    fields = data.model_dump(exclude={"category_ids"})
    try:
        async with in_transaction() as connection:
            movie = await MovieInfo.create(**fields, using_db=connection)
            await _set_movie_categories(movie, data.category_ids, using_db=connection)
            await _write_log(admin, "movie.create", "movie", movie.movieid, {"category_ids": data.category_ids}, using_db=connection)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="电影 ID 已存在") from exc
    return {"code": 201, "data": {"movieid": movie.movieid}}


@router.put("/{movieid}")
async def update_movie(movieid: int, data: MovieUpdate, admin: AdminUser = Depends(auth.get_current_admin)):
    movie = await MovieInfo.get_or_none(movieid=movieid, deleted_at=None)
    if movie is None:
        raise HTTPException(status_code=404, detail="电影不存在或已删除")
    changes = data.model_dump(exclude_unset=True)
    category_ids = changes.pop("category_ids", None)
    if not changes and category_ids is None:
        raise HTTPException(status_code=422, detail="至少提供一个需要修改的字段")
    async with in_transaction() as connection:
        for key, value in changes.items():
            setattr(movie, key, value)
        if changes:
            await movie.save(update_fields=[*changes.keys(), "updated_at"], using_db=connection)
        if category_ids is not None:
            await _set_movie_categories(movie, category_ids, using_db=connection)
        await _write_log(admin, "movie.update", "movie", movieid, {**changes, "category_ids": category_ids}, using_db=connection)
    return {"code": 200, "msg": "电影更新成功"}


@router.delete("/{movieid}")
async def delete_movie(movieid: int, admin: AdminUser = Depends(auth.get_current_admin)):
    movie = await MovieInfo.get_or_none(movieid=movieid, deleted_at=None)
    if movie is None:
        raise HTTPException(status_code=404, detail="电影不存在或已删除")
    async with in_transaction() as connection:
        movie.deleted_at = datetime.now(timezone.utc)
        await movie.save(update_fields=["deleted_at", "updated_at"], using_db=connection)
        await _write_log(admin, "movie.delete", "movie", movieid, using_db=connection)
    return {"code": 200, "msg": "电影已软删除"}


@router.post("/categories", status_code=201)
async def create_category(data: CategoryCreate, admin: AdminUser = Depends(auth.get_current_admin)):
    try:
        async with in_transaction() as connection:
            category = await Category.create(name=data.name, using_db=connection)
            await _write_log(admin, "category.create", "category", category.categoryid, {"name": category.name}, using_db=connection)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="分类名称已存在") from exc
    return {"code": 201, "data": {"categoryid": category.categoryid, "name": category.name}}


@router.put("/categories/{categoryid}")
async def update_category(categoryid: int, data: CategoryUpdate, admin: AdminUser = Depends(auth.get_current_admin)):
    category = await Category.get_or_none(categoryid=categoryid, deleted_at=None)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在或已删除")
    category.name = data.name
    try:
        async with in_transaction() as connection:
            await category.save(update_fields=["name"], using_db=connection)
            await _write_log(admin, "category.update", "category", categoryid, {"name": category.name}, using_db=connection)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="分类名称已存在") from exc
    return {"code": 200, "msg": "分类更新成功"}


@router.delete("/categories/{categoryid}")
async def delete_category(categoryid: int, admin: AdminUser = Depends(auth.get_current_admin)):
    category = await Category.get_or_none(categoryid=categoryid, deleted_at=None)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在或已删除")
    async with in_transaction() as connection:
        category.deleted_at = datetime.now(timezone.utc)
        await category.save(update_fields=["deleted_at"], using_db=connection)
        await MovieCategory.filter(category_id=categoryid).using_db(connection).delete()
        await _write_log(admin, "category.delete", "category", categoryid, {"name": category.name}, using_db=connection)
    return {"code": 200, "msg": "分类已软删除"}


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
    cache_key = f"movies:list:{q or ''}:{category_id or 0}:{sort_by}:{order}:{page}:{page_size}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
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
    result = {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
    await cache_set(cache_key, result, ttl=120)
    return result


@router.get("/{movieid}")
async def get_movie_detail(movieid: int):
    movie = await MovieInfo.filter(
        movieid=movieid,
        deleted_at=None,
    ).first()
    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="电影不存在或已删除",
        )
    movie_data = {
        "movieid": movie.movieid,
        "moviename": movie.moviename,
        "releasetime": movie.releasetime,
        "director": movie.director,
        "leadactors": movie.leadactors,
        "picture": movie.picture,
        "averating": movie.averating,
        "numrating": movie.numrating,
        "description": movie.description,
        "typelist": movie.typelist,
    }
    category_ids = await MovieCategory.filter(movie_id=movieid).values_list("category_id", flat=True)
    movie_data["categories"] = await Category.filter(
        categoryid__in=category_ids,
        deleted_at=None,
    ).values("categoryid", "name")
    return {"code": 200, "data": movie_data}
