from pathlib import Path
import re

from tortoise.backends.base.client import BaseDBAsyncClient


RUN_IN_TRANSACTION = False


async def upgrade(db: BaseDBAsyncClient | None) -> str:
    if db is None:
        return ""

    migration_path = Path(__file__).resolve().parents[2] / "0001_schema_upgrade.sql"
    script = migration_path.read_text(encoding="utf-8")
    script = re.sub(r"(?im)^\s*USE\s+`movierecommend`\s*;\s*", "", script, count=1)

    required_tables = (
        "user", "movieinfo", "personalratings", "trainingdataset", "trainingrating",
        "category", "moviecategory", "moviecomment", "commentlike",
        "commentlike_event", "adminuser", "commentreport", "userfavorite",
        "adminoperationlog", "recommendationitem", "recommendationevent",
    )
    schema_state = await db.execute_query_dict(
        """
        SELECT TABLE_NAME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN (%s)
        """
        % ",".join("'" + table + "'" for table in required_tables)
    )
    present_tables = {row["TABLE_NAME"] for row in schema_state}
    metadata_table_sql = """
    CREATE TABLE IF NOT EXISTS `aerich` (
      `id` int NOT NULL AUTO_INCREMENT,
      `version` varchar(255) NOT NULL,
      `app` varchar(100) NOT NULL,
      `content` json NOT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    if len(present_tables) == len(required_tables):
        return metadata_table_sql

    if {"trainingdataset", "trainingrating", "category", "moviecategory"}.issubset(present_tables):
        marker = "-- Normalize the existing comma-separated typelist"
        return metadata_table_sql + marker + script.split(marker, 1)[1]
    return metadata_table_sql + script


async def downgrade(db: BaseDBAsyncClient) -> str:
    return ""


MODELS_STATE = (
    "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"
    "4="
)
