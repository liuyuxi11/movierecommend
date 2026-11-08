"""Synthetic Spark smoke test; no database access or external writes."""

from __future__ import annotations

import logging
import os
import sys
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
    per_user_random_split,
)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker_python = os.environ.get("PYSPARK_PYTHON", sys.executable)
    spark = (SparkSession.builder.master("local[2]").appName("als-synthetic-smoke")
             .config("spark.sql.session.timeZone", "UTC")
             .config("spark.sql.shuffle.partitions", "4")
             .config("spark.pyspark.python", worker_python)
             .config("spark.driver.host", "127.0.0.1")
             .config("spark.driver.bindAddress", "127.0.0.1").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    run_id = uuid.uuid4().hex
    logger = RunAdapter(logging.getLogger("als_smoke"), {"run_id": run_id})
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
            rank=2, max_iter=3, reg_param=0.1, seed=42, checkpoint_interval=-1,
            als_blocks=2, top_n=3, positive_threshold=4, candidate_multiplier=3,
            baseline_pool=8, fallback_pool=8, batch_id="smoketest2026",
            model_version="als-smoke-hybrid-v1", bayes_prior_strength=2.0,
            max_ranking_pairs=1000, ranking_user_sample=100,
            selected_hybrid_weight=0.5,
        )
        train, valid, test, _, _, sizes = per_user_random_split(ratings, args)
        print("split rows:", sizes, flush=True)
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

        singleton = spark.createDataFrame(
            [(1, 1, 1, 5.0, base)],
            "ratingid long, userId int, movieId int, rating float, rated_at timestamp",
        )
        try:
            per_user_random_split(singleton, args)
        except ValueError as exc:
            assert "empty partition" in str(exc)
        else:
            raise AssertionError("empty per-user split should fail explicitly")

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
            methods=("als", "popularity", "bayesian", "random", "hybrid"),
        )
        print("ranking evaluation complete", flush=True)
        assert {"als", "popularity", "bayesian", "random", "hybrid_pop_0.5", "evaluation_scope"} == set(ranking)
        output = fill_and_publish_candidates(
            model, ratings, active_users, active_movies, category_map, args, logger
        )
        print("candidate generation complete", flush=True)
        assert output.filter((F.col("position") < 1) | (F.col("position") > args.top_n)).count() == 0
        assert output.groupBy("request_id", "movieid").count().filter(F.col("count") > 1).count() == 0
        assert output.filter(F.col("userid") == 99).count() > 0
        assert output.groupBy("userid").count().filter(F.col("count") < args.top_n).count() == 0
        print("synthetic ALS smoke passed; ranking methods:", sorted(ranking))
        for frame in (ratings, train, valid, test):
            frame.unpersist()
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
