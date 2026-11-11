from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app import auth
from app.analytics import (
    calculate_recommendation_rates,
    get_recommendation_event_counts,
    get_system_counts,
)
from app.models import AdminUser


router = APIRouter()


@router.get("/overview")
async def analytics_overview(
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
    admin: AdminUser = Depends(auth.get_current_admin),
):
    end = end_at or datetime.now(timezone.utc)
    start = start_at or end - timedelta(days=30)
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_at 和 end_at 必须包含时区")
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if start >= end:
        raise HTTPException(status_code=422, detail="start_at 必须早于 end_at")

    event_counts = await get_recommendation_event_counts(start, end)
    return {
        "code": 200,
        "data": {
            "counts": await get_system_counts(),
            "recommendations": {
                **calculate_recommendation_rates(event_counts),
                "window": {"start_at": start, "end_at": end},
            },
        },
    }
