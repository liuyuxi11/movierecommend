"""Synthetic Spark smoke test; no database access or external writes."""

from __future__ import annotations

import logging
from pathlib import Path
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from pyspark.sql import SparkSession, functions as F

from als_recommender import (
    RunAdapter,
    als_estimator,
    evaluate_ranking_methods,
    fill_and_publish_candidates,
    regression_metrics,
    temporal_split,
)


def main():
    spark = (SparkSession.builder.master("local[2]").appName("als-synthetic-smoke")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    run_id = uuid.uuid4().hex
    logger = RunAdapter(logging.getLogger("als_smoke"), {"run_id": run_id})
    checkpoint = (Path(tempfile.gettempdir()) / ("als-smoke-checkpoint-" + run_id)).resolve().as_uri()
    spark.sparkContext.setCheckpointDir(checkpoint)
    try:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = []
        rating_id = 1
        for user in range(1, 5):
            for offset in range(5):
                movie = ((user * 3 + offset) % 8) + 1
                rows.append((rating_id, user, movie, float(((user + offset) % 5) + 1),
                             base + timedelta(days=offset)))
                rating_id += 1
        ratings = spark.createDataFrame(
            rows, "ratingid long, userId int, movieId int, rating float, rated_at timestamp"
        ).cache()
        args = SimpleNamespace(
            train_cutoff="2026-01-03T00:00:00Z", valid_cutoff="2026-01-04T00:00:00Z",
            rank=2, max_iter=3, reg_param=0.1, seed=42, checkpoint_interval=2,
            als_blocks=2, top_n=3, positive_threshold=4, candidate_multiplier=3,
            baseline_pool=8, fallback_pool=8, batch_id="smoketest2026",
            model_version="als-smoke-hybrid-v1",
        )
        train, valid, test, _, _, sizes = temporal_split(ratings, args)
        assert all(size > 0 for size in sizes), sizes
        model = als_estimator(args, args.rank, args.max_iter, args.reg_param).fit(train.unionByName(valid))
        regression = regression_metrics(model, test, logger, "synthetic-test")
        assert 0 < regression["prediction_coverage"] <= 1
        cold = spark.createDataFrame(
            [(999, 10, 5.0, base + timedelta(days=5))],
            "userId int, movieId int, rating float, rated_at timestamp",
        )
        try:
            regression_metrics(model, cold, logger, "synthetic-cold-start")
        except ValueError as exc:
            assert "no predictable rows" in str(exc)
        else:
            raise AssertionError("cold-start-only regression evaluation should fail explicitly")

        empty_split_args = SimpleNamespace(
            train_cutoff="2030-01-01T00:00:00Z", valid_cutoff="2031-01-01T00:00:00Z"
        )
        try:
            temporal_split(ratings, empty_split_args)
        except ValueError as exc:
            assert "empty partition" in str(exc)
        else:
            raise AssertionError("empty temporal partition should fail explicitly")

        active_users = spark.createDataFrame([(1,), (2,), (3,), (4,), (99,)], "userId int")
        active_movies = spark.createDataFrame(
            [(movie, 7.5) for movie in range(1, 11)], "movieId int, movie_rating_snapshot double"
        ).withColumn("movie_rating_snapshot", F.col("movie_rating_snapshot").cast("decimal(4,1)"))
        category_map = spark.createDataFrame(
            [(movie, (movie % 3) + 1) for movie in range(1, 11)], "movieId int, categoryid int"
        )
        ranking = evaluate_ranking_methods(
            model, train.unionByName(valid), test, active_users,
            active_movies.select("movieId"), category_map, args, logger, [],
        )
        assert {"als", "popularity", "random"} == set(ranking)
        output = fill_and_publish_candidates(
            model, ratings, active_users, active_movies, category_map, args, logger
        )
        assert output.filter((F.col("position") < 1) | (F.col("position") > args.top_n)).count() == 0
        assert output.groupBy("request_id", "movieid").count().filter(F.col("count") > 1).count() == 0
        assert output.filter(F.col("userid") == 99).count() > 0
        print("synthetic ALS smoke passed; ranking methods:", sorted(ranking))
        for frame in (ratings, train, valid, test):
            frame.unpersist()
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
