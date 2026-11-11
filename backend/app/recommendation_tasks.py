"""Publish precomputed ALS recommendations for one Celery request."""

import asyncio
import json
import logging
import math
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

import asyncmy

from app.celery_app import celery_app
from app.database import DATABASE_URL, close_db, init_db
from app.models import MovieInfo, PersonalRating, RecommendationEvent, RecommendationItem, User
from app.redis_cache import cache_set_checked, close_redis, read_hot_cache_ids, refresh_hot_cache


LOG = logging.getLogger(__name__)
TOP_N = 20
CACHE_TTL = int(os.getenv("RECOMMENDATION_CACHE_TTL", "300"))
OFFLINE_RANK_WEIGHT = float(os.getenv("RECOMMENDATION_OFFLINE_RANK_WEIGHT", "0.75"))
POPULARITY_RANK_WEIGHT = float(os.getenv("RECOMMENDATION_POPULARITY_RANK_WEIGHT", "0.10"))
PROFILE_RANK_WEIGHT = float(os.getenv("RECOMMENDATION_PROFILE_RANK_WEIGHT", "0.15"))
CLICK_BOOST = float(os.getenv("RECOMMENDATION_CLICK_BOOST", "0.10"))
FEEDBACK_LOOKBACK_DAYS = int(os.getenv("RECOMMENDATION_FEEDBACK_LOOKBACK_DAYS", "90"))
EXPECTED_DATABASE = "movierecommend_test"

RANK_WEIGHTS = (OFFLINE_RANK_WEIGHT, POPULARITY_RANK_WEIGHT, PROFILE_RANK_WEIGHT)
if not all(math.isfinite(weight) and weight >= 0 for weight in RANK_WEIGHTS):
    raise ValueError("Recommendation ranking weights must be non-negative")
if sum(RANK_WEIGHTS) <= 0:
    raise ValueError("At least one recommendation ranking weight must be positive")
RANKING_VERSION = (
    f"als-personalized-rerank-v1-o{OFFLINE_RANK_WEIGHT:g}"
    f"-p{POPULARITY_RANK_WEIGHT:g}-g{PROFILE_RANK_WEIGHT:g}-f{CLICK_BOOST:g}"
)


def _assert_test_database() -> None:
    if os.getenv("RECOMMENDATION_WRITE_ENABLED") != "YES":
        raise RuntimeError("Set RECOMMENDATION_WRITE_ENABLED=YES to enable test recommendation writes")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be configured")
    database = unquote(urlsplit(DATABASE_URL).path.lstrip("/"))
    if database != EXPECTED_DATABASE:
        raise RuntimeError("Recommendation source reads are restricted to movierecommend_test")
    write_url = os.getenv("RECOMMENDATION_WRITE_URL")
    if not write_url or unquote(urlsplit(write_url).path.lstrip("/")) != EXPECTED_DATABASE:
        raise RuntimeError("RECOMMENDATION_WRITE_URL must target movierecommend_test")


def _load_als_for_user(user_id: int) -> list[dict]:
    root = Path(os.environ["ALS_RECOMMENDATION_ROOT"]).resolve()
    pointer_path = root / "latest.json"
    if not pointer_path.is_file():
        return []
    with pointer_path.open("r", encoding="utf-8") as stream:
        pointer = json.load(stream)
    if pointer.get("format") != "jsonl-v1" or not pointer.get("batch_id"):
        raise ValueError("Invalid ALS recommendation manifest")
    users_dir = Path(pointer["users_dir"]).resolve()
    if root not in users_dir.parents:
        raise ValueError("ALS recommendation manifest points outside the configured shared root")
    user_path = users_dir / f"{user_id}.jsonl"
    if not user_path.is_file():
        return []
    results = []
    with user_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if int(row["userid"]) != user_id:
                raise ValueError("ALS JSONL user id does not match requested user")
            results.append(row)
    return sorted(results, key=lambda row: (int(row["position"]), int(row["movieid"])))


def feedback_adjusted_score(score: float, event_types: set[str]) -> float | None:
    """Apply recent explicit negative feedback and a bounded click boost."""
    if "not_interested" in event_types:
        return None
    return min(1.0, score + CLICK_BOOST) if "click" in event_types else score


async def _build_response(user_id: int, request_id: str, rows: list[dict]) -> dict:
    movie_ids = [int(row["movie_id"]) for row in rows]
    movies = await MovieInfo.filter(movieid__in=movie_ids, deleted_at=None)
    movie_map = {movie.movieid: movie for movie in movies}
    items = []
    for position, row in enumerate(rows, start=1):
        movie = movie_map.get(int(row["movie_id"]))
        if movie is None:
            continue
        score = row.get("prediction_score")
        version = str(row.get("algorithm_version") or "")
        current_score = version.startswith("als-personalized-rerank-v1")
        items.append({
            "movieid": movie.movieid,
            "moviename": movie.moviename,
            "picture": movie.picture,
            "position": position,
            "prediction_score": float(score) if score is not None and current_score else None,
            "recommendation_source": (
                "popular_fallback" if "popular-fallback" in version
                else "als_rerank" if current_score
                else "legacy"
            ),
        })
    return {"code": 200, "request_id": request_id, "items": items}


async def _existing_request(user_id: int, request_id: str):
    rows = await RecommendationItem.filter(request_id=request_id).order_by("position").values(
        "user_id", "movie_id", "position", "prediction_score", "algorithm_version",
    )
    if not rows:
        return None
    if any(row["user_id"] != user_id for row in rows):
        raise RuntimeError("request_id already belongs to a different user")
    return rows


async def _insert_recommendation_rows(records: list[RecommendationItem]) -> None:
    parsed = urlsplit(os.environ["RECOMMENDATION_WRITE_URL"])
    connection = await asyncmy.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        db=unquote(parsed.path.lstrip("/")),
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
        read_timeout=30,
    )
    insert_sql = """
        INSERT INTO recommendationitem
          (request_id, userid, movieid, position, movie_rating_snapshot,
           prediction_score, algorithm_version, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT DATABASE()")
            database_row = await cursor.fetchone()
            if not database_row or database_row[0] != EXPECTED_DATABASE:
                raise RuntimeError("Active recommendation writer is not connected to movierecommend_test")
            await cursor.executemany(insert_sql, [(
                row.request_id, row.user_id, row.movie_id, row.position,
                row.movie_rating_snapshot, row.prediction_score,
                row.algorithm_version, row.generated_at.replace(tzinfo=None),
            ) for row in records])
        await connection.commit()
    except Exception:
        await connection.rollback()
        raise
    finally:
        connection.close()


async def _generate(user_id: int, request_id: str) -> dict:
    _assert_test_database()
    await init_db()
    try:
        existing = await _existing_request(user_id, request_id)
        if existing is not None:
            response = await _build_response(user_id, request_id, existing)
            cache_written = await cache_set_checked(
                f"recommendation:{user_id}:latest", response, ttl=CACHE_TTL
            )
            return {"request_id": request_id, "count": len(response["items"]),
                    "reused": True, "cache_written": cache_written}

        user = await User.get_or_none(userid=user_id, deleted_at=None)
        if user is None:
            raise ValueError("Cannot generate recommendations for a missing or deleted user")
        ratings = await PersonalRating.filter(user_id=user_id).select_related("movie").all()
        seen = {int(rating.movie_id) for rating in ratings}
        genre_totals: dict[str, list[float]] = {}
        for rating in ratings:
            if rating.movie.deleted_at is not None:
                continue
            genres = str(rating.movie.typelist or "").split(",")
            normalized_rating = (float(rating.rating) - 1.0) / 4.0
            for genre in {value.strip().casefold() for value in genres if value.strip()}:
                total = genre_totals.setdefault(genre, [0.0, 0.0])
                total[0] += normalized_rating
                total[1] += 1.0
        genre_preferences = {
            genre: total / count for genre, (total, count) in genre_totals.items()
        }

        feedback_rows = await (
            RecommendationEvent.filter(
                recommendation__user_id=user_id,
                created_at__gte=datetime.now(timezone.utc) - timedelta(days=FEEDBACK_LOOKBACK_DAYS),
                event_type__in=["click", "not_interested"],
            )
            .values("recommendation__movie_id", "event_type")
        )
        feedback_by_movie: dict[int, set[str]] = {}
        for row in feedback_rows:
            feedback_by_movie.setdefault(int(row["recommendation__movie_id"]), set()).add(row["event_type"])

        als_rows = _load_als_for_user(user_id)
        als_ids = [int(row["movieid"]) for row in als_rows]
        if len(als_ids) != len(set(als_ids)):
            raise ValueError("ALS JSONL contains duplicate movie ids for one user")
        valid_als = await MovieInfo.filter(movieid__in=als_ids, deleted_at=None)
        movie_map = {movie.movieid: movie for movie in valid_als}
        als_ranked = []
        for row in als_rows:
            movie_id = int(row["movieid"])
            if movie_id in seen or movie_id not in movie_map:
                continue
            als_ranked.append({
                "movie": movie_map[movie_id],
                "offline_position": len(als_ranked) + 1,
                "algorithm_version": RANKING_VERSION,
            })

        hot_ids = await read_hot_cache_ids(limit=max(TOP_N * 5, 100))
        if hot_ids:
            hot_rows = await MovieInfo.filter(movieid__in=hot_ids, deleted_at=None)
            hot_map = {movie.movieid: movie for movie in hot_rows}
            hot_movies = [hot_map[movie_id] for movie_id in hot_ids if movie_id in hot_map]
        else:
            hot_movies = await MovieInfo.filter(deleted_at=None).order_by(
                "-averating", "-numrating", "movieid"
            ).limit(max(TOP_N * 5, 100))
            await refresh_hot_cache([
                (movie.movieid, float(movie.averating or 0) * 1_000_000 + float(movie.numrating or 0))
                for movie in hot_movies
            ], ttl=max(CACHE_TTL, 3600))

        candidates_by_id = {item["movie"].movieid: item for item in als_ranked}
        hot_count = len(hot_movies)
        hot_denominator = max(hot_count - 1, 1)
        for hot_position, movie in enumerate(hot_movies, start=1):
            if movie.movieid in seen:
                continue
            item = candidates_by_id.get(movie.movieid)
            if item is None:
                item = {
                    "movie": movie,
                    "offline_position": None,
                    "algorithm_version": RANKING_VERSION + "+popular-fallback",
                }
                candidates_by_id[movie.movieid] = item
            item["popularity_score"] = 1.0 - (hot_position - 1) / hot_denominator

        als_count = max(len(als_ranked), 1)
        # Ordinal and profile signals share a bounded 0-1 scale; this is a
        # list-local ranking value, not an ALS rating prediction.
        for item in candidates_by_id.values():
            movie = item["movie"]
            genres = {value.strip().casefold() for value in str(movie.typelist or "").split(",") if value.strip()}
            item["offline_rank_score"] = (
                1.0 - (item["offline_position"] - 1) / als_count
                if item["offline_position"] is not None else 0.0
            )
            item["profile_score"] = (
                sum(genre_preferences[genre] for genre in genres if genre in genre_preferences)
                / len([genre for genre in genres if genre in genre_preferences])
                if any(genre in genre_preferences for genre in genres) else None
            )
            item["popularity_score"] = item.get("popularity_score")
            active_weights = []
            if item["offline_position"] is not None:
                active_weights.append((OFFLINE_RANK_WEIGHT, item["offline_rank_score"]))
            if item["popularity_score"] is not None:
                active_weights.append((POPULARITY_RANK_WEIGHT, item["popularity_score"]))
            if item["profile_score"] is not None:
                active_weights.append((PROFILE_RANK_WEIGHT, item["profile_score"]))
            if not any(weight > 0 for weight, _ in active_weights):
                fallback_signal = next((
                    (1.0, item[key]) for key in (
                        "popularity_score", "profile_score", "offline_rank_score",
                    )
                    if item.get(key) is not None
                ), (1.0, 0.0))
                active_weights = [fallback_signal]
            weight_total = sum(weight for weight, _ in active_weights)
            item["score"] = (
                sum(weight * value for weight, value in active_weights) / weight_total
                if weight_total else 0.0
            )
            item["score"] = feedback_adjusted_score(
                item["score"], feedback_by_movie.get(movie.movieid, set())
            )

        candidates = sorted(
            (item for item in candidates_by_id.values() if item["score"] is not None),
            key=lambda item: (-item["score"], item["movie"].movieid),
        )[:TOP_N]

        if len({item["movie"].movieid for item in candidates}) != len(candidates):
            raise ValueError("Candidate list contains duplicate movie ids")
        if any(item["movie"].deleted_at is not None for item in candidates):
            raise ValueError("Candidate list contains a soft-deleted movie")

        response_items = [{
            "movieid": item["movie"].movieid,
            "moviename": item["movie"].moviename,
            "picture": item["movie"].picture,
            "position": position,
            "prediction_score": round(float(item["score"]), 6),
            "recommendation_source": "popular_fallback" if "popular-fallback" in item["algorithm_version"] else "als_rerank",
        } for position, item in enumerate(candidates, start=1)]
        response = {"code": 200, "request_id": request_id, "items": response_items}

        if candidates:
            now = datetime.now(timezone.utc)
            records = [RecommendationItem(
                request_id=request_id,
                user_id=user_id,
                movie_id=item["movie"].movieid,
                position=position,
                movie_rating_snapshot=(
                    Decimal(str(item["movie"].averating))
                    if item["movie"].averating is not None else None
                ),
                prediction_score=Decimal(str(round(float(item["score"]), 6))),
                algorithm_version=item["algorithm_version"],
                generated_at=now,
            ) for position, item in enumerate(candidates, start=1)]

            # Source rows were read with the read-only ORM account. This separate
            # connection must have INSERT permission only on recommendationitem.
            await _insert_recommendation_rows(records)

        # Redis is updated only after MySQL commit. Cache failure never rolls back
        # durable results; the API can read MySQL and refill the cache.
        cache_written = await cache_set_checked(
            f"recommendation:{user_id}:latest", response, ttl=CACHE_TTL
        )
        hot_pool_available = bool(hot_movies)

        LOG.info(
            "recommendation_published request_id=%s user_id=%s items=%s algorithm=%s cache_written=%s hot_pool_available=%s",
            request_id, user_id, len(candidates), RANKING_VERSION, cache_written, hot_pool_available,
        )
        return {"request_id": request_id, "count": len(candidates), "reused": False,
                "cache_written": cache_written, "hot_pool_available": hot_pool_available}
    finally:
        try:
            await close_db()
        finally:
            await close_redis()


@celery_app.task(
    name="recommendation.generate",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
)
def generate_recommendation_task(self, user_id: int, request_id: str) -> dict:
    UUID(request_id)
    return asyncio.run(_generate(user_id, request_id))


@celery_app.task(
    name="recommendation.refresh_user",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2},
    retry_backoff=True,
)
def refresh_user_recommendations_task(self, user_id: int, request_id: str) -> dict:
    UUID(request_id)
    return asyncio.run(_generate(user_id, request_id))


@celery_app.task(
    name="recommendation.train_als",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(subprocess.SubprocessError, OSError),
    retry_kwargs={"max_retries": 1},
    retry_backoff=True,
)
def train_als_candidates_task(self) -> dict:
    """Run the offline Spark job and atomically publish its JSONL manifest."""
    project_root = Path(__file__).resolve().parents[2]
    job_path = project_root / "backend" / "jobs" / "als_recommender.py"
    publish_root = Path(os.environ["ALS_RECOMMENDATION_ROOT"]).resolve()
    timeout = int(os.getenv("ALS_TRAIN_TIMEOUT_SECONDS", "14400"))
    command = [
        sys.executable,
        str(job_path),
        "--no-snapshot",
        "--jsonl-recommendations-root",
        str(publish_root),
    ]
    subprocess.run(
        command,
        cwd=project_root,
        check=True,
        timeout=timeout,
    )
    manifest_path = publish_root / "latest.json"
    with manifest_path.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("format") != "jsonl-v1" or not manifest.get("batch_id"):
        raise RuntimeError("ALS job completed without publishing a valid JSONL manifest")
    LOG.info("als_candidates_published batch_id=%s", manifest["batch_id"])
    return {"batch_id": manifest["batch_id"], "users_dir": manifest["users_dir"]}
