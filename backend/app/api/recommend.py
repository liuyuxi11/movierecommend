from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.celery_app import celery_app
from app.models import MovieInfo, RecommendationEvent, RecommendationItem, User
from app.redis_cache import cache_delete, cache_get, cache_set

router = APIRouter()


class RecommendEvent(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    movieid: int = Field(gt=0)
    event_type: Literal["impression", "click", "not_interested"]


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_recommendation(current_user: User = Depends(get_current_user)):
    request_id = uuid4().hex
    try:
        task = celery_app.send_task("recommendation.generate", args=[current_user.userid, request_id])
    except Exception as exc:
        raise HTTPException(status_code=503, detail="推荐任务队列不可用，请启动 Redis 和 Celery Worker") from exc
    await cache_delete(f"recommendation:{current_user.userid}:latest")
    return {"code": 202, "request_id": request_id, "task_id": task.id, "msg": "推荐任务已提交"}


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
    ).order_by("position").values("movie_id", "position", "prediction_score")
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
            "prediction_score": row["prediction_score"],
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
    query = MovieInfo.filter(deleted_at=None).exclude(movieid=movieid)
    if movie.typelist:
        first_type = next((item.strip() for item in movie.typelist.split(",") if item.strip()), None)
        if first_type:
            query = query.filter(typelist__icontains=first_type)
    rows = await query.order_by("-averating", "-numrating", "movieid").limit(limit).values(
        "movieid", "moviename", "picture", "averating", "numrating", "releasetime"
    )
    return {"code": 200, "data": rows}


@router.post("/event")
async def record_event(data: RecommendEvent, current_user: User = Depends(get_current_user)):
    item = await RecommendationItem.get_or_none(
        request_id=data.request_id, movie_id=data.movieid, user_id=current_user.userid,
    )
    if item is None or not await MovieInfo.filter(movieid=data.movieid, deleted_at=None).exists():
        raise HTTPException(status_code=404, detail="找不到当前用户的有效推荐记录")
    await RecommendationEvent.create(recommendation_id=item.recommendationid, event_type=data.event_type)
    return {"code": 200, "msg": "事件已记录"}
