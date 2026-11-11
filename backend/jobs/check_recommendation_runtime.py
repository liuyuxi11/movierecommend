"""Check Redis, Celery broker/worker, and test database configuration safely."""

from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import unquote, urlsplit

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.celery_app import REDIS_URL, celery_app  # noqa: E402
from app.redis_cache import get_redis  # noqa: E402


def database_name(url: str | None) -> str | None:
    if not url:
        return None
    return unquote(urlsplit(url).path.lstrip("/")) or None


def jdbc_database_name(url: str | None) -> str | None:
    if not url or not url.lower().startswith("jdbc:mysql://"):
        return None
    return unquote(urlsplit(url[5:]).path.lstrip("/")) or None


def main() -> int:
    checks = {}
    try:
        redis_version = version("redis")
        checks["redis_package"] = True
        print(f"redis_package_version={redis_version}")
    except PackageNotFoundError:
        checks["redis_package"] = False
    checks["redis_url_configured"] = bool(os.getenv("REDIS_URL"))
    checks["celery_app_available"] = hasattr(celery_app, "connection_for_read")
    checks["celery_broker_matches_cache"] = REDIS_URL == os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    checks["celery_result_backend_configured"] = bool(celery_app.conf.result_backend)
    checks["celery_result_backend_matches_cache"] = (
        celery_app.conf.result_backend == os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
    )
    checks["celery_json_only"] = set(celery_app.conf.accept_content or []) == {"json"}
    checks["recommendation_write_enabled"] = os.getenv("RECOMMENDATION_WRITE_ENABLED") == "YES"
    checks["recommendation_database_is_test"] = (
        database_name(os.getenv("DATABASE_URL")) == "movierecommend_test"
    )
    checks["recommendation_writer_configured"] = bool(os.getenv("RECOMMENDATION_WRITE_URL"))
    checks["recommendation_writer_database_is_test"] = (
        database_name(os.getenv("RECOMMENDATION_WRITE_URL")) == "movierecommend_test"
    )
    checks["als_jdbc_database_is_test"] = (
        jdbc_database_name(os.getenv("MYSQL_JDBC_URL")) == "movierecommend_test"
    )
    checks["als_shared_root_configured"] = bool(os.getenv("ALS_RECOMMENDATION_ROOT"))

    try:
        import asyncio

        asyncio.run(get_redis().ping())
        checks["redis_ping"] = True
    except Exception as exc:
        checks["redis_ping"] = False
        print(f"redis_ping_error={type(exc).__name__}")

    try:
        with celery_app.connection_for_read() as connection:
            connection.ensure_connection(max_retries=0)
        checks["celery_broker_connection"] = True
    except Exception as exc:
        checks["celery_broker_connection"] = False
        print(f"celery_broker_error={type(exc).__name__}")

    try:
        replies = celery_app.control.inspect(timeout=2.0).ping() or {}
        checks["celery_worker_online"] = bool(replies)
        checks["celery_worker_count"] = len(replies)
    except Exception as exc:
        checks["celery_worker_online"] = False
        checks["celery_worker_error"] = type(exc).__name__

    for name, value in checks.items():
        print(f"{name}={value}")
    required = (
        "redis_ping", "celery_broker_connection", "celery_worker_online",
        "recommendation_write_enabled", "recommendation_database_is_test",
        "recommendation_writer_configured", "recommendation_writer_database_is_test",
        "als_jdbc_database_is_test", "als_shared_root_configured",
    )
    ready = all(checks.get(name) for name in required)
    print(f"recommendation_runtime_ready={ready}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
