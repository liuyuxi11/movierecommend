import os
from datetime import timedelta

try:
    from celery import Celery
except ImportError:
    Celery = None
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
if Celery is None:
    class _UnavailableCelery:
        def send_task(self, *args, **kwargs):
            raise RuntimeError("celery package is not installed")
    celery_app = _UnavailableCelery()
else:
    celery_app = Celery(
        "movierecommend",
        broker=REDIS_URL,
        backend=os.getenv("CELERY_RESULT_BACKEND", REDIS_URL),
        include=["app.recommendation_tasks"],
    )
    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        broker_connection_timeout=3,
        broker_connection_max_retries=1,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
        task_publish_retry=True,
        task_publish_retry_policy={
            "max_retries": 1,
            "interval_start": 0,
            "interval_step": 0.2,
            "interval_max": 0.5,
        },
        beat_schedule={
            "publish-als-candidates": {
                "task": "recommendation.train_als",
                "schedule": timedelta(
                    seconds=max(60, int(os.getenv("ALS_TRAIN_INTERVAL_SECONDS", "604800")))
                ),
            },
        },
    )
