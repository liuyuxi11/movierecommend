from typing import Literal
from uuid import uuid4
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from tortoise.expressions import Q

from app.auth import get_current_user
from app.celery_app import celery_app
from app.models import MovieCategory, MovieInfo, RecommendationEvent, RecommendationItem, User
from app.redis_cache import cache_delete, cache_get, cache_set, cache_set_checked

router = APIRouter()
TASK_OWNER_TTL = int(os.getenv("RECOMMENDATION_TASK_TTL", "86400"))


class RecommendEvent(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    movieid: int = Field(gt=0)
    event_type: Literal["impression", "click", "not_interested"]


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_recommendation(current_user: User = Depends(get_current_user)):
    request_id = uuid4().hex
    task_id = request_id
    owner_key = f"recommendation:task-owner:{task_id}"
    if not await cache_set_checked(owner_key, current_user.userid, ttl=TASK_OWNER_TTL):
        raise HTTPException(status_code=503, detail="推荐任务状态缓存不可用")
    await cache_delete(f"recommendation:{current_user.userid}:latest")
    try:
        celery_app.send_task(
            "recommendation.generate",
            args=[current_user.userid, request_id],
            task_id=task_id,
        )
    except Exception as exc:
        await cache_delete(owner_key)
        raise HTTPException(status_code=503, detail="推荐任务队列不可用，请启动 Redis 和 Celery Worker") from exc
    return {"code": 202, "request_id": request_id, "task_id": task_id, "msg": "推荐任务已提交"}


@router.get("/task/{task_id}")
async def get_recommendation_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    owner = await cache_get(f"recommendation:task-owner:{task_id}")
    if owner is None:
        raise HTTPException(status_code=404, detail="任务不存在或状态已过期")
    if int(owner) != current_user.userid:
        raise HTTPException(status_code=404, detail="任务不存在或状态已过期")
    result = celery_app.AsyncResult(task_id)
    payload = {"code": 200, "task_id": task_id, "state": result.state}
    if result.state == "SUCCESS":
        payload["result"] = result.result
    elif result.state == "FAILURE":
        payload["error"] = type(result.result).__name__
    return payload


async def _recommendation_result(user_id: int):
    cache_key = f"recommendation:{user_id}:latest"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    latest = await RecommendationItem.filter(user_id=user_id).order_by("-generated_at", "-recommendationid").first()
    if latest is None:
        result = {"code": 200, "request_id": None, "items": []}
        await cache_set(cache_key, result, ttl=300)
        return result
    rows = await RecommendationItem.filter(
        request_id=latest.request_id, user_id=user_id,
    ).order_by("position").values(
        "movie_id", "position", "prediction_score", "algorithm_version",
    )
    movie_rows = await MovieInfo.filter(
        movieid__in=[row["movie_id"] for row in rows], deleted_at=None,
    ).values("movieid", "moviename", "picture")
    movie_map = {row["movieid"]: row for row in movie_rows}
    items = [
        {
            "movieid": row["movie_id"],
            "moviename": movie_map[row["movie_id"]]["moviename"],
            "picture": movie_map[row["movie_id"]]["picture"],
            "position": row["position"],
            "prediction_score": (
                row["prediction_score"]
                if str(row["algorithm_version"] or "").startswith("als-personalized-rerank-v1")
                else None
            ),
            "recommendation_source": (
                "popular_fallback"
                if "popular-fallback" in str(row["algorithm_version"] or "")
                else "als_rerank"
                if str(row["algorithm_version"] or "").startswith("als-personalized-rerank-v1")
                else "legacy"
            ),
        }
        for row in rows if row["movie_id"] in movie_map
    ]
    result = {"code": 200, "request_id": latest.request_id, "items": items}
    await cache_set(cache_key, result, ttl=300)
    return result


@router.get("/result")
async def get_recommendation_result(current_user: User = Depends(get_current_user)):
    return await _recommendation_result(current_user.userid)


@router.get("/result/{userid}")
async def get_recommendation_result_for_user(userid: int, current_user: User = Depends(get_current_user)):
    if userid != current_user.userid:
        raise HTTPException(status_code=403, detail="不能查询其他用户的推荐结果")
    return await _recommendation_result(userid)


@router.get("/similar/{movieid}")
async def get_similar_movies(movieid: int, limit: int = Query(10, ge=1, le=50)):
    movie = await MovieInfo.get_or_none(movieid=movieid, deleted_at=None)
    if movie is None:
        raise HTTPException(status_code=404, detail="电影不存在或已删除")
    source_categories = set(await MovieCategory.filter(movie_id=movieid).values_list("category_id", flat=True))
    if source_categories:
        candidate_ids = await (
            MovieCategory.filter(category_id__in=source_categories)
            .exclude(movie_id=movieid)
            .order_by("movie_id")
            .distinct()
            .limit(5000)
            .values_list("movie_id", flat=True)
        )
        candidate_categories = await MovieCategory.filter(movie_id__in=candidate_ids).values(
            "movie_id", "category_id",
        )
        category_map: dict[int, set[int]] = {}
        for row in candidate_categories:
            category_map.setdefault(row["movie_id"], set()).add(row["category_id"])
        similarity_sets = {movie_id: values for movie_id, values in category_map.items()}
        source_set = source_categories
    else:
        source_set = {
            value.strip().casefold()
            for value in str(movie.typelist or "").split(",")
            if value.strip()
        }
        tokens = sorted(source_set)
        if not tokens:
            return {"code": 200, "data": []}
        type_query = Q(typelist__icontains=tokens[0])
        for token in tokens[1:]:
            type_query |= Q(typelist__icontains=token)
        fallback_ids = await (
            MovieInfo.filter(deleted_at=None)
            .exclude(movieid=movieid)
            .filter(type_query)
            .order_by("movieid")
            .limit(5000)
            .values_list("movieid", flat=True)
        )
        similarity_sets = {
            row["movieid"]: {
                value.strip().casefold()
                for value in str(row["typelist"] or "").split(",")
                if value.strip()
            }
            for row in await MovieInfo.filter(movieid__in=fallback_ids, deleted_at=None).values(
                "movieid", "typelist",
            )
        }

    candidate_ids = list(similarity_sets)
    candidates = await MovieInfo.filter(
        movieid__in=candidate_ids,
        deleted_at=None,
    ).values("movieid", "moviename", "picture", "averating", "numrating", "releasetime")
    ranked = []
    for row in candidates:
        candidate_set = similarity_sets[row["movieid"]]
        union = source_set | candidate_set
        similarity = len(source_set & candidate_set) / len(union) if union else 0.0
        if similarity > 0:
            ranked.append({**row, "similarity_score": round(similarity, 6)})
    ranked.sort(
        key=lambda row: (
            -row["similarity_score"],
            -(row["averating"] or 0),
            -(row["numrating"] or 0),
            row["movieid"],
        )
    )
    return {"code": 200, "data": ranked[:limit]}


@router.post("/event")
async def record_event(data: RecommendEvent, current_user: User = Depends(get_current_user)):
    item = await RecommendationItem.get_or_none(
        request_id=data.request_id, movie_id=data.movieid, user_id=current_user.userid,
    )
    if item is None or not await MovieInfo.filter(movieid=data.movieid, deleted_at=None).exists():
        raise HTTPException(status_code=404, detail="找不到当前用户的有效推荐记录")
    await RecommendationEvent.create(recommendation_id=item.recommendationid, event_type=data.event_type)
    return {"code": 200, "msg": "事件已记录"}
