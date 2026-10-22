"""Read-side aggregation queries for dashboard and recommendation analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tortoise.functions import Avg, Count

from app.models import (
    CommentReport,
    MovieComment,
    PersonalRating,
    RecommendationEvent,
    UserFavorite,
)


async def get_rating_distribution() -> list[dict[str, Any]]:
    """Return counts grouped by the current 1-10 rating value."""
    return await (
        PersonalRating.all()
        .group_by("rating")
        .annotate(total=Count("ratingid"))
        .values("rating", "total")
    )


async def get_movie_rating_summaries() -> list[dict[str, Any]]:
    """Return current average and rating count for each movie with ratings."""
    return await (
        PersonalRating.all()
        .group_by("movie_id")
        .annotate(
            average_rating=Avg("rating"),
            rating_count=Count("ratingid"),
        )
        .values("movie_id", "average_rating", "rating_count")
    )


async def get_comment_moderation_counts() -> list[dict[str, Any]]:
    """Count non-deleted comments by moderation state."""
    return await (
        MovieComment.filter(deleted_at__isnull=True)
        .group_by("moderation_status")
        .annotate(total=Count("commentid"))
        .values("moderation_status", "total")
    )


async def get_report_status_counts() -> list[dict[str, Any]]:
    """Count reports by pending/accepted/rejected status."""
    return await (
        CommentReport.all()
        .group_by("status")
        .annotate(total=Count("reportid"))
        .values("status", "total")
    )


async def get_active_favorite_counts() -> list[dict[str, Any]]:
    """Count active favorites by want-to-watch/watched state."""
    return await (
        UserFavorite.filter(deleted_at__isnull=True)
        .group_by("status")
        .annotate(total=Count("id"))
        .values("status", "total")
    )


async def get_recommendation_event_counts(
    start_at: datetime,
    end_at: datetime,
) -> list[dict[str, Any]]:
    """Count recommendation events in the half-open UTC interval [start, end)."""
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise ValueError("start_at and end_at must be timezone-aware UTC datetimes")
    if start_at.utcoffset() is None or end_at.utcoffset() is None:
        raise ValueError("start_at and end_at must be timezone-aware UTC datetimes")
    if start_at >= end_at:
        raise ValueError("start_at must be earlier than end_at")

    return await (
        RecommendationEvent.filter(
            created_at__gte=start_at,
            created_at__lt=end_at,
        )
        .group_by("event_type")
        .annotate(total=Count("eventid"))
        .values("event_type", "total")
    )
