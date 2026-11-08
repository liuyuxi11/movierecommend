"""Transactionally publish a Parquet recommendation batch to recommendationitem.

This is intentionally separate from ALS training. It requires an explicit CLI
confirmation, an environment opt-in, and the expected target database name.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from urllib.parse import unquote, urlsplit

import pymysql
from pyspark.sql import SparkSession, functions as F


TOKEN_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")
REQUIRED_COLUMNS = {
    "request_id", "userid", "movieid", "position", "movie_rating_snapshot",
    "prediction_score", "algorithm_version", "generated_at",
}
LOG = logging.getLogger("recommendation_loader")


def connect():
    parsed = urlsplit(os.environ["MYSQL_WRITE_URL"])
    return pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=unquote(parsed.path.lstrip("/")),
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
        read_timeout=120,
        write_timeout=120,
    )


def chunks(values, size=500):
    values = list(values)
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def validate_file(spark, path: str, batch_id: str, top_n: int):
    frame = spark.read.parquet(path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Parquet is missing columns: {sorted(missing)}")
    if frame.limit(1).count() == 0:
        raise ValueError("Refusing to publish an empty recommendation batch")

    invalid = frame.filter(
        F.col("request_id").isNull()
        | (F.col("request_id") != F.concat(F.lit(batch_id + "-"), F.col("userid").cast("string")))
        | F.col("userid").isNull() | F.col("movieid").isNull()
        | F.col("position").isNull() | (F.col("position") < 1)
        | (F.col("position") > top_n)
        | F.col("prediction_score").isNull()
        | F.isnan(F.col("prediction_score").cast("double"))
        | (F.col("prediction_score") < -9999.999999)
        | (F.col("prediction_score") > 9999.999999)
        | (F.col("movie_rating_snapshot") < -999.9)
        | (F.col("movie_rating_snapshot") > 999.9)
        | F.isnan(F.col("movie_rating_snapshot").cast("double"))
        | F.col("algorithm_version").isNull()
        | F.col("generated_at").isNull()
        | (F.length("algorithm_version") > 100)
    )
    if invalid.limit(1).count():
        raise ValueError("Batch contains null, malformed, or out-of-range fields")

    duplicate_movies = frame.groupBy("request_id", "movieid").count().filter(F.col("count") > 1)
    duplicate_positions = frame.groupBy("request_id", "position").count().filter(F.col("count") > 1)
    if duplicate_movies.limit(1).count() or duplicate_positions.limit(1).count():
        raise ValueError("Batch violates unique request/movie or request/position invariants")

    bad_position_groups = frame.groupBy("request_id").agg(
        F.min("position").alias("min_position"), F.max("position").alias("max_position"),
        F.countDistinct("position").alias("positions"),
    ).filter(
        (F.col("min_position") != 1)
        | (F.col("max_position") != F.col("positions"))
    )
    if bad_position_groups.limit(1).count():
        raise ValueError("Each request must have contiguous positions starting at 1")
    return frame


def verify_parent_rows(cursor, user_ids: set[int], movie_ids: set[int]) -> None:
    active_users = set()
    for part in chunks(user_ids):
        marks = ",".join(["%s"] * len(part))
        cursor.execute(f"SELECT userid FROM `user` WHERE deleted_at IS NULL AND userid IN ({marks})", part)
        active_users.update(row[0] for row in cursor.fetchall())
    active_movies = set()
    for part in chunks(movie_ids):
        marks = ",".join(["%s"] * len(part))
        cursor.execute(f"SELECT movieid FROM movieinfo WHERE deleted_at IS NULL AND movieid IN ({marks})", part)
        active_movies.update(row[0] for row in cursor.fetchall())
    missing_users = user_ids - active_users
    missing_movies = movie_ids - active_movies
    if missing_users or missing_movies:
        raise ValueError(
            f"FK/active-entity validation failed: users={len(missing_users)}, movies={len(missing_movies)}"
        )


def publish(frame, connection, batch_id: str, batch_size: int) -> tuple[int, str]:
    # Collect only distinct entity keys for FK checks. Recommendation rows are
    # streamed to the driver in bounded batches within one InnoDB transaction.
    entity_rows = frame.select("userid", "movieid").distinct().collect()
    user_ids = {int(row.userid) for row in entity_rows}
    movie_ids = {int(row.movieid) for row in entity_rows}
    request_pattern = batch_id + "-%"
    insert_sql = """
      INSERT INTO recommendationitem
        (request_id, userid, movieid, position, movie_rating_snapshot,
         prediction_score, algorithm_version, generated_at)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE()")
            database_name = cursor.fetchone()[0]
            expected_database = os.environ["EXPECTED_RECOMMENDATION_DATABASE"]
            if database_name != expected_database:
                raise ValueError("Connected database does not match EXPECTED_RECOMMENDATION_DATABASE")
            cursor.execute("SET SESSION time_zone = '+00:00'")
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute("START TRANSACTION")
            verify_parent_rows(cursor, user_ids, movie_ids)

            # Exact retry is implemented as transactional replacement. A prior
            # batch with feedback cannot be deleted because recommendationevent
            # has a RESTRICT FK; aborting then preserves the entire prior batch.
            cursor.execute(
                "SELECT COUNT(*) FROM recommendationitem WHERE request_id LIKE %s",
                (request_pattern,),
            )
            existing = cursor.fetchone()[0]
            if existing:
                cursor.execute(
                    "SELECT COUNT(*) FROM recommendationevent e "
                    "JOIN recommendationitem i ON i.recommendationid=e.recommendationid "
                    "WHERE i.request_id LIKE %s",
                    (request_pattern,),
                )
                if cursor.fetchone()[0]:
                    raise ValueError("Batch already has feedback events; use a new batch ID")
                cursor.execute("DELETE FROM recommendationitem WHERE request_id LIKE %s", (request_pattern,))

            verify_parent_rows(cursor, user_ids, movie_ids)
            pending = []
            inserted = 0
            for row in frame.toLocalIterator():
                pending.append((
                    row.request_id, int(row.userid), int(row.movieid), int(row.position),
                    row.movie_rating_snapshot, row.prediction_score,
                    row.algorithm_version, row.generated_at,
                ))
                if len(pending) >= batch_size:
                    cursor.executemany(insert_sql, pending)
                    inserted += len(pending)
                    pending.clear()
            if pending:
                cursor.executemany(insert_sql, pending)
                inserted += len(pending)
        connection.commit()
        return inserted, database_name
    except Exception:
        connection.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--top-n", required=True, type=int)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--confirm-mysql-write", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not TOKEN_RE.fullmatch(args.batch_id):
        parser.error("batch-id must be 1-32 alphanumeric characters")
    if not args.confirm_mysql_write or os.getenv("ALLOW_RECOMMENDATION_MYSQL_WRITE") != "YES":
        parser.error("writing requires --confirm-mysql-write and ALLOW_RECOMMENDATION_MYSQL_WRITE=YES")
    if args.batch_size < 1 or args.top_n < 1:
        parser.error("batch-size and top-n must be positive")
    os.environ["EXPECTED_RECOMMENDATION_DATABASE"] = args.expected_database

    spark = None
    connection = None
    try:
        spark = SparkSession.builder.appName("recommendation-transactional-loader").getOrCreate()
        frame = validate_file(spark, args.parquet, args.batch_id, args.top_n)
        connection = connect()
        actual_database = unquote(urlsplit(os.environ["MYSQL_WRITE_URL"]).path.lstrip("/"))
        if actual_database != args.expected_database:
            raise ValueError("MYSQL_WRITE_URL database does not match --expected-database")
        inserted, database_name = publish(frame, connection, args.batch_id, args.batch_size)
        LOG.info("published rows=%s batch_id=%s database=%s", inserted, args.batch_id, database_name)
        return 0
    except Exception:
        LOG.exception("publish_failed batch_id=%s", args.batch_id)
        return 1
    finally:
        if connection is not None:
            connection.close()
        if spark is not None:
            spark.stop()


if __name__ == "__main__":
    sys.exit(main())
