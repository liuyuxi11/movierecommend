from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.auth import get_current_user
from app.models import MovieInfo, RecommendationEvent, RecommendationItem, User


router = APIRouter()


class RecommendEvent(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    movieid: int = Field(gt=0)
    event_type: Literal["impression", "click", "not_interested"]


@router.post("/generate")
async def generate_recommendation(
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="推荐生成任务服务尚未配置",
    )


@router.get("/result")
async def get_recommendation_result(
    current_user: User = Depends(get_current_user),
):
    latest = await RecommendationItem.filter(
        user_id=current_user.userid,
    ).order_by("-generated_at", "-recommendationid").first()

    if latest is None:
        return {"code": 200, "request_id": None, "items": []}

    rows = await RecommendationItem.filter(
        request_id=latest.request_id,
        user_id=current_user.userid,
    ).order_by("position").values(
        "movie_id",
        "position",
        "prediction_score",
    )
    if not rows:
        return {"code": 200, "request_id": latest.request_id, "items": []}

    movie_rows = await MovieInfo.filter(
        movieid__in=[row["movie_id"] for row in rows],
        deleted_at=None,
    ).values("movieid", "moviename")
    movie_names = {row["movieid"]: row["moviename"] for row in movie_rows}
    items = [
        {
            "movieid": row["movie_id"],
            "moviename": movie_names[row["movie_id"]],
            "position": row["position"],
            "prediction_score": row["prediction_score"],
        }
        for row in rows
        if row["movie_id"] in movie_names
    ]
    return {"code": 200, "request_id": latest.request_id, "items": items}


@router.post("/event")
async def record_event(
    data: RecommendEvent,
    current_user: User = Depends(get_current_user),
):
    item = await RecommendationItem.get_or_none(
        request_id=data.request_id,
        movie_id=data.movieid,
        user_id=current_user.userid,
    )
    movie_exists = await MovieInfo.filter(
        movieid=data.movieid,
        deleted_at=None,
    ).exists()
    if item is None or not movie_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到当前用户的有效推荐记录",
        )

    await RecommendationEvent.create(
        recommendation_id=item.recommendationid,
        event_type=data.event_type,
    )
    return {"code": 200, "msg": "事件已记录"}
