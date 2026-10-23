import os

from dotenv import load_dotenv
from tortoise import Tortoise


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Aerich imports this configuration through backend/pyproject.toml.
TORTOISE_ORM = {
    "connections": {"default": DATABASE_URL},
    "apps": {
        "models": {
            "models": ["app.models", "aerich.models"],
            "default_connection": "default",
        }
    },
    "use_tz": True,
    "timezone": "UTC",
}


async def init_db() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be configured in the environment")

    await Tortoise.init(
        db_url=DATABASE_URL,
        modules={"models": ["app.models"]},
        use_tz=True,
        timezone="UTC",
        _enable_global_fallback=True,
    )


async def close_db() -> None:
    await Tortoise.close_connections()
