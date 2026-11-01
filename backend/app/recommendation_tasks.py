import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.celery_app import celery_app
from app.database import close_db, init_db
from app.models import MovieInfo, PersonalRating, RecommendationItem
from app.redis_cache import cache_delete


async def _generate(user_id: int, request_id: str) -> int:
    """Persist recommendations; the ALS provider should replace the ranking query below.

    Keep task dispatch and result persistence here. The algorithm module should
    return ordered movie IDs with scores and an algorithm version.
    """
    await init_db()
    try:
        rated_ids = set(await PersonalRating.filter(user_id=user_id).values_list("movie_id", flat=True))
        query = MovieInfo.filter(deleted_at=None)
        if rated_ids:
            query = query.exclude(movieid__in=rated_ids)
        movies = await query.order_by("-averating", "-numrating", "movieid").limit(20)
        now = datetime.now(timezone.utc)
        records = [
            RecommendationItem(
                request_id=request_id,
                user_id=user_id,
                movie_id=movie.movieid,
                position=position,
                movie_rating_snapshot=Decimal(str(movie.averating)) if movie.averating is not None else None,
                prediction_score=Decimal(str(movie.averating)) if movie.averating is not None else None,
                algorithm_version="popularity-v1",
                generated_at=now,
            )
            for position, movie in enumerate(movies, start=1)
        ]
        if records:
            await RecommendationItem.bulk_create(records)
        return len(records)
    finally:
        await close_db()


@celery_app.task(name="recommendation.generate")
def generate_recommendation_task(user_id: int, request_id: str) -> dict:
    UUID(request_id)
    count = asyncio.run(_generate(user_id, request_id))
    asyncio.run(cache_delete(f"recommendation:{user_id}:latest"))
    return {"request_id": request_id, "count": count}
