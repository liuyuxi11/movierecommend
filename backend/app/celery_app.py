import os

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
    )
