"""Tortoise ORM configuration for the MySQL application database."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv


load_dotenv()


def _database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required. Set it to the MySQL URL for the target database."
        )
    return database_url


TORTOISE_ORM: dict[str, Any] = {
    "connections": {
        "default": _database_url(),
    },
    "apps": {
        "models": {
            "models": ["app.models", "aerich.models"],
            "default_connection": "default",
        },
    },
    "use_tz": True,
    "timezone": "UTC",
}
