"""Read-only MySQL extraction and explicit ALS evaluation/recommendation job."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import tempfile
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pyspark import __version__ as SPARK_VERSION
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.recommendation import ALS
from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.sql.window import Window


LOG = logging.getLogger("movie_als")
ID_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class RunAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"run_id={self.extra['run_id']} {msg}", kwargs


def validate_jdbc_url(url: str) -> None:
    parsed = url.lower()
    if not parsed.startswith("jdbc:mysql://"):
        raise ValueError("MYSQL_JDBC_URL must use jdbc:mysql://")
    if not re.search(r"(?:[?&])servertimezone=utc(?:&|$)", parsed):
        raise ValueError("MYSQL_JDBC_URL must explicitly include serverTimezone=UTC")


def jdbc_read(spark: SparkSession, query: str, args, *, partition_column=None, bounds=None) -> DataFrame:
    url = os.environ["MYSQL_JDBC_URL"]
    validate_jdbc_url(url)
    reader = (
        spark.read.format("jdbc")
        .option("url", url)
        .option("driver", "com.mysql.cj.jdbc.Driver")
        .option("user", os.environ["MYSQL_USER"])
        .option("password", os.environ["MYSQL_PASSWORD"])
        .option("dbtable", f"({query}) AS src")
        .option("fetchsize", str(args.jdbc_fetch_size))
    )
    if partition_column and args.jdbc_partitions > 1 and bounds:
        lower, upper = bounds
        if lower is not None and upper is not None and lower < upper:
            reader = (
                reader.option("partitionColumn", partition_column)
                .option("lowerBound", str(lower))
                .option("upperBound", str(upper))
                .option("numPartitions", str(args.jdbc_partitions))
            )
    return reader.load()


def extract_database_snapshot(spark: SparkSession, args) -> tuple[DataFrame, DataFrame, DataFrame, DataFrame, DataFrame, dict]:
    if args.input_snapshot:
        root = args.input_snapshot.rstrip("/\\")
        ratings = spark.read.parquet(root + "/ratings").cache()
        active_users = spark.read.parquet(root + "/active_users").cache()
        active_movies = spark.read.parquet(root + "/active_movies").cache()
        category_map = spark.read.parquet(root + "/movie_categories").cache()
        quality_path = Path(root) / "quality.json"
        if not quality_path.is_file():
            raise ValueError("Snapshot is missing quality.json; recapture it to preserve source quality statistics")
        with quality_path.open("r", encoding="utf-8") as stream:
            quality = json.load(stream)
        if quality["duplicate_user_movie_keys"] or quality["invalid_rating"]:
            raise ValueError("Input Parquet snapshot violates rating uniqueness/range invariants")
        return ratings, ratings, active_users, active_movies, category_map, quality

    # One LEFT JOIN extract lets the job count orphan/deleted rows explicitly.
    ratings_sql = """
      SELECT pr.ratingid, pr.userid, pr.movieid, pr.rating, pr.rated_at,
             u.userid AS joined_userid, u.deleted_at AS user_deleted_at,
             m.movieid AS joined_movieid, m.deleted_at AS movie_deleted_at
      FROM personalratings pr
      LEFT JOIN `user` u ON u.userid = pr.userid
      LEFT JOIN movieinfo m ON m.movieid = pr.movieid
    """
    bounds_sql = "SELECT MIN(ratingid) AS lo, MAX(ratingid) AS hi FROM personalratings"
    bounds_df = jdbc_read(spark, bounds_sql, args)
    bounds_row = bounds_df.first()
    ratings = jdbc_read(
        spark, ratings_sql, args,
        partition_column="ratingid",
        bounds=(bounds_row.lo, bounds_row.hi),
    ).cache()

    raw_count = ratings.count()
    quality = ratings.agg(
        F.sum(F.col("userid").isNull().cast("long")).alias("null_userid"),
        F.sum(F.col("movieid").isNull().cast("long")).alias("null_movieid"),
        F.sum(F.col("rating").isNull().cast("long")).alias("null_rating"),
        F.sum(F.col("rated_at").isNull().cast("long")).alias("null_rated_at"),
        F.sum(F.col("joined_userid").isNull().cast("long")).alias("orphan_user"),
        F.sum(F.col("joined_movieid").isNull().cast("long")).alias("orphan_movie"),
        F.sum((F.col("user_deleted_at").isNotNull()).cast("long")).alias("deleted_user_rows"),
        F.sum((F.col("movie_deleted_at").isNotNull()).cast("long")).alias("deleted_movie_rows"),
        F.sum((~F.col("rating").between(1, 5)).cast("long")).alias("invalid_rating"),
    ).first().asDict()

    duplicate_count = (
        ratings.groupBy("userid", "movieid").count()
        .filter(F.col("count") > 1).count()
    )
    quality["duplicate_user_movie_keys"] = duplicate_count
    trainable = (
        ratings
        .filter(
            F.col("joined_userid").isNotNull()
            & F.col("joined_movieid").isNotNull()
            & F.col("user_deleted_at").isNull()
            & F.col("movie_deleted_at").isNull()
            & F.col("rating").between(1, 5)
            & F.col("rated_at").isNotNull()
        )
        .select(
            F.col("ratingid").cast("long"),
            F.col("userid").cast("int").alias("userId"),
            F.col("movieid").cast("int").alias("movieId"),
            F.col("rating").cast("float"),
            F.col("rated_at").cast("timestamp").alias("rated_at"),
        )
        .cache()
    )
    quality["trainable_rows"] = trainable.count()
    quality["filtered_rows"] = raw_count - quality["trainable_rows"]
    if quality["trainable_rows"] == 0:
        trainable.unpersist()
        raise ValueError("No trainable ratings after quality and soft-delete filtering")

    users_sql = "SELECT userid FROM `user` WHERE deleted_at IS NULL"
    movies_sql = "SELECT movieid, averating FROM movieinfo WHERE deleted_at IS NULL"
    active_users = jdbc_read(spark, users_sql, args).select(F.col("userid").cast("int").alias("userId"))
    active_movies = jdbc_read(spark, movies_sql, args).select(
        F.col("movieid").cast("int").alias("movieId"),
        F.col("averating").cast("decimal(4,1)").alias("movie_rating_snapshot"),
    )
    if args.snapshot_path:
        quality["source"] = "mysql_personalratings_joined_entities"
        quality["input_rows"] = raw_count
        trainable.write.mode("errorifexists").parquet(args.snapshot_path.rstrip("/\\") + "/ratings")
        active_users.write.mode("errorifexists").parquet(args.snapshot_path.rstrip("/\\") + "/active_users")
        active_movies.write.mode("errorifexists").parquet(args.snapshot_path.rstrip("/\\") + "/active_movies")
    category_sql = """
      SELECT mc.movieid AS movieId, c.categoryid
      FROM moviecategory mc JOIN category c ON c.categoryid=mc.categoryid
      JOIN movieinfo m ON m.movieid=mc.movieid AND m.deleted_at IS NULL
      WHERE c.deleted_at IS NULL
    """
    category_map = jdbc_read(spark, category_sql, args).select(
        F.col("movieId").cast("int"), F.col("categoryid").cast("int")
    ).cache()
    if args.snapshot_path:
        category_map.write.mode("errorifexists").parquet(args.snapshot_path.rstrip("/\\") + "/movie_categories")
        write_json(args.snapshot_path.rstrip("/\\") + "/quality.json", quality)
    return ratings, trainable, active_users, active_movies, category_map, quality


def temporal_split(ratings: DataFrame, args):
    if args.train_cutoff and args.valid_cutoff:
        train_cutoff = datetime.fromisoformat(args.train_cutoff.replace("Z", "+00:00"))
        valid_cutoff = datetime.fromisoformat(args.valid_cutoff.replace("Z", "+00:00"))
        if train_cutoff.tzinfo is None or valid_cutoff.tzinfo is None or train_cutoff >= valid_cutoff:
            raise ValueError("cutoffs must be timezone-aware and train-cutoff < valid-cutoff")
        train_cutoff = train_cutoff.astimezone(timezone.utc)
        valid_cutoff = valid_cutoff.astimezone(timezone.utc)
    elif args.train_cutoff or args.valid_cutoff:
        raise ValueError("Provide both --train-cutoff and --valid-cutoff, or neither")
    else:
        quantiles = ratings.select(F.col("rated_at").cast("double").alias("epoch"))\
            .approxQuantile("epoch", [0.80, 0.90], 0.001)
        if len(quantiles) != 2:
            raise ValueError("Unable to calculate temporal cutoffs")
        train_cutoff = datetime.fromtimestamp(quantiles[0], timezone.utc)
        valid_cutoff = datetime.fromtimestamp(quantiles[1], timezone.utc)

    train = ratings.filter(F.col("rated_at") <= F.lit(train_cutoff)).cache()
    valid = ratings.filter(
        (F.col("rated_at") > F.lit(train_cutoff))
        & (F.col("rated_at") <= F.lit(valid_cutoff))
    ).cache()
    test = ratings.filter(F.col("rated_at") > F.lit(valid_cutoff)).cache()
    sizes = (train.count(), valid.count(), test.count())
    if any(size == 0 for size in sizes):
        train.unpersist()
        valid.unpersist()
        test.unpersist()
        raise ValueError(f"Temporal split produced an empty partition: train/valid/test={sizes}")
    return train, valid, test, train_cutoff, valid_cutoff, sizes


def als_estimator(args, rank: int, iterations: int, reg_param: float) -> ALS:
    return ALS(
        userCol="userId", itemCol="movieId", ratingCol="rating",
        rank=rank, maxIter=iterations, regParam=reg_param,
        implicitPrefs=False, nonnegative=False, coldStartStrategy="drop",
        seed=args.seed, checkpointInterval=args.checkpoint_interval,
        numUserBlocks=args.als_blocks, numItemBlocks=args.als_blocks,
    )


def regression_metrics(model, data: DataFrame, logger, label: str) -> dict:
    total = data.count()
    predictions = model.transform(data).cache()
    try:
        predicted = predictions.filter(F.col("prediction").isNotNull() & ~F.isnan("prediction"))
        predicted_count = predicted.count()
        coverage = predicted_count / total if total else 0.0
        result = {"total_rows": total, "predictable_rows": predicted_count,
                  "prediction_coverage": coverage}
        if predicted_count == 0:
            logger.error("regression_metrics %s", json.dumps({"dataset": label, **result}, sort_keys=True))
            raise ValueError(
                f"{label}: no predictable rows after cold-start drop "
                f"(total_rows={total}, predictable_rows=0, prediction_coverage=0)"
            )
        for metric in ("rmse", "mae"):
            evaluator = RegressionEvaluator(labelCol="rating", predictionCol="prediction", metricName=metric)
            value = evaluator.evaluate(predicted)
            if not math.isfinite(value):
                raise ValueError(f"{label}: {metric} is not finite")
            result[metric] = value
        logger.info("regression_metrics %s", json.dumps({"dataset": label, **result}, sort_keys=True))
        return result
    finally:
        predictions.unpersist()


def topk_metrics(recommendations: DataFrame, relevant: DataFrame, catalog: DataFrame,
                 category_map: DataFrame, users: DataFrame, k: int, logger, label: str) -> dict:
    relevant_users = relevant.select("userId").distinct()
    ranked = (recommendations.filter(F.col("position") <= k)
              .join(relevant_users, "userId", "inner")
              .select("userId", "movieId", "position"))
    hits = ranked.join(relevant, ["userId", "movieId"], "inner").groupBy("userId").agg(
        F.countDistinct("movieId").alias("hits"),
        F.sum(1.0 / F.log2(F.col("position") + 1)).alias("dcg"),
    )
    per_user = (
        relevant_users.join(hits, "userId", "left")
        .join(relevant.groupBy("userId").agg(F.countDistinct("movieId").alias("relevant_count")), "userId")
        .fillna({"hits": 0, "dcg": 0.0})
        .withColumn("precision", F.col("hits") / F.lit(k))
        .withColumn("recall", F.col("hits") / F.col("relevant_count"))
        .withColumn("ideal_hits", F.least(F.col("relevant_count"), F.lit(k)))
        .withColumn("idcg", F.expr("aggregate(sequence(1, cast(ideal_hits as int)), cast(0.0 as double), (a, x) -> a + 1.0 / log2(x + 1))"))
        .withColumn("ndcg", F.when(F.col("idcg") > 0, F.col("dcg") / F.col("idcg")).otherwise(0.0))
    )
    averages = per_user.agg(
        F.avg("precision").alias("precision_at_k"),
        F.avg("recall").alias("recall_at_k"),
        F.avg("ndcg").alias("ndcg_at_k"),
        F.count("*").alias("evaluated_users"),
    ).first().asDict()
    evaluated = int(averages["evaluated_users"] or 0)
    if evaluated == 0:
        raise ValueError(f"{label}: no test users have relevant items at threshold")

    recommended_items = ranked.select("movieId").distinct()
    catalog_count = catalog.select("movieId").distinct().count()
    coverage_items = recommended_items.count()
    recommended_users = ranked.select("userId").distinct().count()
    user_count = users.select("userId").distinct().count()

    # Category coverage is the fraction of recommended items' category tags
    # represented in each list. This is a bounded category variety proxy, not
    # pairwise intra-list distance.
    category_rows = ranked.join(category_map, "movieId", "left")
    user_diversity = (
        category_rows.groupBy("userId")
        .agg(F.countDistinct("categoryid").alias("category_count"),
             F.countDistinct("movieId").alias("movie_count"))
        .withColumn("diversity", F.when(F.col("movie_count") > 0,
                                         F.least(F.col("category_count"), F.col("movie_count"))
                                         / F.col("movie_count")).otherwise(0.0))
    )
    diversity_by_user = (relevant_users.join(user_diversity.select("userId", "diversity"), "userId", "left")
                         .fillna({"diversity": 0.0}))
    diversity = diversity_by_user.agg(F.avg("diversity")).first()[0] or 0.0
    result = {
        **{key: float(value or 0.0) for key, value in averages.items() if key != "evaluated_users"},
        "evaluated_users": evaluated,
        "item_coverage": coverage_items / catalog_count if catalog_count else 0.0,
        "warm_test_user_list_coverage": recommended_users / evaluated if evaluated else 0.0,
        "active_user_list_coverage": recommended_users / user_count if user_count else 0.0,
        "mean_category_coverage_ratio": float(diversity),
        "candidate_policy": "shared active catalog with model item factors; exclude train-seen; cold-start test users excluded",
    }
    logger.info("ranking_metrics %s", json.dumps({"dataset": label, "k": k, **result}, sort_keys=True))
    return result


def make_ranked_candidates(users: DataFrame, candidate_rows: DataFrame,
                           seen: DataFrame, catalog: DataFrame, k: int) -> DataFrame:
    w = Window.partitionBy("userId").orderBy(F.desc("score"), F.asc("movieId"))
    return (
        candidate_rows.join(seen, ["userId", "movieId"], "left_anti")
        .join(catalog.select("movieId").distinct(), "movieId", "inner")
        .withColumn("position", F.row_number().over(w))
        .filter(F.col("position") <= k)
        .select("userId", "movieId", "position")
    )


def evaluate_ranking_methods(model, train: DataFrame, test: DataFrame, all_active_users: DataFrame,
                             catalog: DataFrame, category_map: DataFrame, args, logger,
                             cache_registry: list[DataFrame]) -> dict:
    seen = train.select("userId", "movieId").distinct()
    factor_movies = model.itemFactors.select(F.col("id").alias("movieId"))
    candidate_catalog = catalog.join(factor_movies, "movieId", "inner").distinct()
    eval_users = test.select("userId").distinct()
    known_users = model.userFactors.select(F.col("id").alias("userId"))
    warm_eval_users = eval_users.join(known_users, "userId", "inner")
    if warm_eval_users.limit(1).count() == 0:
        raise ValueError("No warm test users available for Top-K evaluation")
    # Cold-start users are excluded from ALS ranking metrics and measured
    # separately through the recommendation user-coverage metric.
    relevant = (test.filter(F.col("rating") >= args.positive_threshold)
                .join(warm_eval_users, "userId", "inner")
                .select("userId", "movieId").distinct().cache())
    cache_registry.append(relevant)
    if relevant.limit(1).count() == 0:
        relevant.unpersist()
        raise ValueError("No relevant warm-user test interactions; lower --positive-threshold or inspect split")

    als_raw = (
        model.recommendForUserSubset(warm_eval_users, args.top_n * args.candidate_multiplier)
        .select("userId", F.explode("recommendations").alias("rec"))
        .select("userId", F.col("rec.movieId").alias("movieId"), F.col("rec.rating").alias("score"))
    )
    als_raw = als_raw.filter(
        F.col("score").isNotNull() & ~F.isnan("score")
        & (F.abs(F.col("score")) <= 9999.999999)
    )
    als_ranked = make_ranked_candidates(warm_eval_users, als_raw, seen, candidate_catalog, args.top_n)

    # Popularity scores are calculated only from training rows.
    popularity = train.groupBy("movieId").agg(
        F.count("*").alias("n"), F.avg("rating").alias("avg_rating")
    ).withColumn("score", F.col("n") * F.col("avg_rating"))
    pop_candidates = (
        warm_eval_users.crossJoin(F.broadcast(popularity.orderBy(F.desc("score"), F.asc("movieId"))
                                              .limit(args.baseline_pool)))
        .select("userId", "movieId", "score")
    )
    popular_ranked = make_ranked_candidates(warm_eval_users, pop_candidates, seen, candidate_catalog, args.top_n)

    # Deterministic pseudo-random baseline uses a seeded hash of user/movie IDs.
    random_pool = candidate_catalog.select("movieId").withColumn(
        "sample_key", F.xxhash64("movieId", F.lit(args.seed))
    ).orderBy("sample_key").limit(args.baseline_pool).drop("sample_key")
    random_candidates = warm_eval_users.crossJoin(F.broadcast(random_pool)).select(
        "userId", "movieId",
        (F.xxhash64("userId", "movieId", F.lit(args.seed)) % F.lit(2147483647)).alias("score")
    )
    random_ranked = make_ranked_candidates(warm_eval_users, random_candidates, seen, candidate_catalog, args.top_n)

    results = {}
    for name, ranked, target_users in (
        ("als", als_ranked, all_active_users),
        ("popularity", popular_ranked, all_active_users),
        ("random", random_ranked, all_active_users),
    ):
        results[name] = topk_metrics(
            ranked, relevant, candidate_catalog, category_map, target_users,
            args.top_n, logger, f"test_{name}",
        )
    relevant.unpersist()
    return results


def fill_and_publish_candidates(model, ratings: DataFrame, active_users: DataFrame,
                                active_movies: DataFrame, category_map: DataFrame,
                                args, logger) -> DataFrame:
    seen = ratings.select(F.col("userId"), F.col("movieId")).distinct()
    catalog = active_movies.select("movieId").distinct()
    als_rows = (
        model.recommendForAllUsers(args.top_n * args.candidate_multiplier)
        .select("userId", F.explode("recommendations").alias("rec"))
        .select("userId", F.col("rec.movieId").alias("movieId"),
                F.col("rec.rating").cast("double").alias("score"), F.lit("als").alias("source"))
    )
    als_rows = als_rows.filter(
        F.col("score").isNotNull() & ~F.isnan("score")
        & (F.abs(F.col("score")) <= 9999.999999)
    )
    # Bounded popularity pool fills short ALS lists and supplies new/zero-rating
    # users. It is built only from currently valid training interactions.
    hot_pool = ratings.groupBy("movieId").agg(
        F.count("*").alias("n"), F.avg("rating").alias("avg_rating")
    ).withColumn("score", F.col("n") * F.col("avg_rating"))\
        .orderBy(F.desc("score"), F.asc("movieId")).limit(args.fallback_pool)\
        .select("movieId", F.col("score").cast("double").alias("score"), F.lit("popular").alias("source"))
    als_candidates = (als_rows.join(seen, ["userId", "movieId"], "left_anti")
                      .join(catalog, "movieId", "inner"))
    w = Window.partitionBy("userId").orderBy(F.desc("score"), F.asc("movieId"))
    als_ranked = als_candidates.withColumn("position", F.row_number().over(w))\
        .filter(F.col("position") <= args.top_n)
    als_counts = als_ranked.groupBy("userId").agg(F.max("position").alias("als_count"))
    short_users = (active_users.join(als_counts, "userId", "left")
                   .fillna({"als_count": 0})
                   .filter(F.col("als_count") < args.top_n))
    fallback_candidates = (
        short_users.crossJoin(F.broadcast(hot_pool))
        .join(seen, ["userId", "movieId"], "left_anti")
        .join(als_ranked.select("userId", "movieId"), ["userId", "movieId"], "left_anti")
    )
    fallback_window = Window.partitionBy("userId").orderBy(F.desc("score"), F.asc("movieId"))
    fallback_ranked = (fallback_candidates
                       .withColumn("fallback_position", F.row_number().over(fallback_window))
                       .withColumn("position", F.col("als_count") + F.col("fallback_position"))
                       .filter(F.col("position") <= args.top_n)
                       .select("userId", "movieId", "score", "source", "position"))
    ranked = (als_ranked.select("userId", "movieId", "score", "source", "position")
              .unionByName(fallback_ranked))
    counts = (active_users.join(ranked.groupBy("userId").count(), "userId", "left")
              .fillna({"count": 0}).cache())
    summary = counts.agg(
        F.min("count").alias("min_items"), F.expr("percentile_approx(count, 0.5)").alias("median_items"),
        F.max("count").alias("max_items"), F.sum((F.col("count") < args.top_n).cast("long")).alias("short_lists"),
        F.sum((F.col("count") > 0).cast("long")).alias("users_with_results"),
    ).first().asDict()
    active_user_count = active_users.select("userId").distinct().count()
    recommended_movie_count = ranked.select("movieId").distinct().count()
    catalog_count = catalog.count()
    summary["active_users"] = active_user_count
    summary["active_user_coverage"] = (
        summary["users_with_results"] / active_user_count if active_user_count else 0.0
    )
    summary["unique_recommended_movies"] = recommended_movie_count
    summary["catalog_item_coverage"] = (
        recommended_movie_count / catalog_count if catalog_count else 0.0
    )
    logger.info("recommendation_list_counts %s", json.dumps(summary, sort_keys=True))
    counts.unpersist()
    if ranked.limit(1).count() == 0:
        logger.warning("recommendation output is empty; no active users have unseen ALS/popular candidates")
    # Snapshot and FK validation are repeated by the transactional loader.
    result = (
        ranked.join(active_movies, "movieId", "inner")
        .select(
            F.concat(F.lit(args.batch_id), F.lit("-"), F.col("userId").cast("string")).alias("request_id"),
            F.col("userId").alias("userid"), F.col("movieId").alias("movieid"),
            F.col("position").cast("int"), "movie_rating_snapshot",
            F.col("score").cast("decimal(10,6)").alias("prediction_score"),
            F.lit(args.model_version).alias("algorithm_version"),
            F.current_timestamp().alias("generated_at"),
        )
    )
    too_long = result.filter(F.length("request_id") > 64).limit(1).count()
    if too_long:
        raise ValueError("Generated request_id exceeds recommendationitem.request_id varchar(64)")
    return result


def parse_grid(text: str, cast):
    try:
        values = [cast(value.strip()) for value in text.split(",") if value.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid parameter grid: {text}") from exc
    if not values:
        raise argparse.ArgumentTypeError("Parameter grid cannot be empty")
    return values


def tune_parameters(train: DataFrame, valid: DataFrame, args, logger) -> tuple[int, int, float, list[dict]]:
    ranks = parse_grid(args.rank_grid, int) if args.tune else [args.rank]
    iterations = parse_grid(args.iter_grid, int) if args.tune else [args.max_iter]
    regs = parse_grid(args.reg_grid, float) if args.tune else [args.reg_param]
    if min(ranks) <= 0 or min(iterations) <= 0 or min(regs) < 0:
        raise ValueError("grid ranks/iterations must be positive and regParams non-negative")
    grid_results = []
    for rank in ranks:
        for iters in iterations:
            for reg in regs:
                started = time.monotonic()
                model = als_estimator(args, rank, iters, reg).fit(train)
                metrics = regression_metrics(model, valid, logger, f"validation_r{rank}_i{iters}_reg{reg}")
                row = {"rank": rank, "max_iter": iters, "reg_param": reg,
                       "validation_rmse": metrics["rmse"], "validation_mae": metrics["mae"],
                       "validation_coverage": metrics["prediction_coverage"],
                       "fit_eval_seconds": time.monotonic() - started}
                grid_results.append(row)
                logger.info("tuning_candidate %s", json.dumps(row, sort_keys=True))
    best = min(grid_results, key=lambda row: row["validation_rmse"])
    return best["rank"], best["max_iter"], best["reg_param"], grid_results


def write_json(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rank", type=int, default=64)
    parser.add_argument("--max-iter", type=int, default=15)
    parser.add_argument("--reg-param", type=float, default=0.05)
    parser.add_argument("--tune", action="store_true")
    parser.add_argument("--rank-grid", default="32,64")
    parser.add_argument("--iter-grid", default="10,15")
    parser.add_argument("--reg-grid", default="0.01,0.05")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--positive-threshold", type=int, default=4)
    parser.add_argument("--candidate-multiplier", type=int, default=5)
    parser.add_argument("--baseline-pool", type=int, default=500)
    parser.add_argument("--fallback-pool", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--als-blocks", type=int, default=10)
    parser.add_argument("--checkpoint-interval", type=int, default=10)
    parser.add_argument("--checkpoint-dir", default=os.getenv("ALS_CHECKPOINT_DIR"))
    parser.add_argument("--jdbc-partitions", type=int, default=int(os.getenv("MYSQL_JDBC_PARTITIONS", "1")))
    parser.add_argument("--jdbc-fetch-size", type=int, default=int(os.getenv("MYSQL_FETCH_SIZE", "10000")))
    parser.add_argument("--shuffle-partitions", type=int, default=int(os.getenv("SPARK_SHUFFLE_PARTITIONS", "200")))
    parser.add_argument("--train-cutoff", default=os.getenv("ALS_TRAIN_CUTOFF"))
    parser.add_argument("--valid-cutoff", default=os.getenv("ALS_VALID_CUTOFF"))
    parser.add_argument("--model-version", default="als-explicit-v1")
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--snapshot-path", default=os.getenv("ALS_SNAPSHOT_PATH"))
    parser.add_argument("--input-snapshot", default=os.getenv("ALS_INPUT_SNAPSHOT"))
    parser.add_argument("--recommendations-path", default=None)
    parser.add_argument("--metadata-path", default=None)
    parser.add_argument("--log-level", default=os.getenv("ALS_LOG_LEVEL", "INFO"))
    # No MySQL write exists in this job. Publishing belongs to the separate loader.
    return parser


def run(args) -> dict:
    run_id = str(uuid.uuid4())
    logger = RunAdapter(LOG, {"run_id": run_id})
    if args.batch_id is None:
        args.batch_id = uuid.uuid4().hex
    if not ID_TOKEN_RE.fullmatch(args.batch_id):
        raise ValueError("--batch-id must be a unique 1-32 character alphanumeric token")
    if not args.model_version or len(args.model_version) > 100:
        raise ValueError("--model-version must be 1-100 characters")
    if bool(args.snapshot_path) == bool(args.input_snapshot):
        raise ValueError("provide exactly one of --snapshot-path (capture) or --input-snapshot (replay)")
    if min(args.rank, args.max_iter, args.top_n, args.positive_threshold,
           args.candidate_multiplier, args.baseline_pool, args.fallback_pool,
           args.jdbc_partitions, args.jdbc_fetch_size, args.shuffle_partitions,
           args.als_blocks, args.checkpoint_interval) <= 0:
        raise ValueError("all count, partition, rank, and iteration parameters must be positive")
    if not args.input_snapshot:
        validate_jdbc_url(os.environ["MYSQL_JDBC_URL"])

    started = time.monotonic()
    started_at_utc = datetime.now(timezone.utc)
    spark = None
    cached = []
    try:
        logger.info("job_start batch_id=%s spark_runtime=%s", args.batch_id, SPARK_VERSION)
        spark = (SparkSession.builder.appName("movie-als-recommender")
                 .config("spark.sql.session.timeZone", "UTC")
                 .config("spark.sql.shuffle.partitions", str(args.shuffle_partitions))
                 .getOrCreate())
        checkpoint_dir = args.checkpoint_dir
        if not checkpoint_dir:
            checkpoint_dir = (Path(tempfile.gettempdir()) / "movie-als-checkpoints" / run_id).resolve().as_uri()
        spark.sparkContext.setCheckpointDir(checkpoint_dir)
        stage_started = time.monotonic()
        raw, ratings, active_users, active_movies, category_map, quality = extract_database_snapshot(spark, args)
        cached.extend([raw, ratings])
        if args.input_snapshot:
            cached.extend([active_users, active_movies, category_map])
        logger.info("data_quality %s", json.dumps(quality, sort_keys=True, default=str))
        logger.info("stage_complete name=extract seconds=%.3f", time.monotonic() - stage_started)
        if quality["duplicate_user_movie_keys"]:
            raise ValueError(
                f"Found {quality['duplicate_user_movie_keys']} duplicate (userid,movieid) keys; refusing nondeterministic training"
            )
        logger.info("snapshot_semantics source=%s; rated_at is last current-rating update, not immutable rating history",
                    "parquet_snapshot" if args.input_snapshot else "current MySQL multi-query extraction")

        stage_started = time.monotonic()
        train, valid, test, train_cutoff, valid_cutoff, split_sizes = temporal_split(ratings, args)
        cached.extend([train, valid, test])
        logger.info("temporal_split %s", json.dumps({
            "train_rows": split_sizes[0], "valid_rows": split_sizes[1], "test_rows": split_sizes[2],
            "train_cutoff_utc": train_cutoff.isoformat(), "valid_cutoff_utc": valid_cutoff.isoformat(),
        }, sort_keys=True))
        logger.info("stage_complete name=temporal_split seconds=%.3f", time.monotonic() - stage_started)

        stage_started = time.monotonic()
        best_rank, best_iter, best_reg, tuning = tune_parameters(train, valid, args, logger)
        logger.info("stage_complete name=tune seconds=%.3f", time.monotonic() - stage_started)
        stage_started = time.monotonic()
        evaluation_model = als_estimator(args, best_rank, best_iter, best_reg).fit(train.unionByName(valid))
        test_regression = regression_metrics(evaluation_model, test, logger, "time_holdout_test")
        logger.info("stage_complete name=test_evaluation seconds=%.3f", time.monotonic() - stage_started)

        if not args.input_snapshot:
            cached.extend([active_users, active_movies, category_map])
        stage_started = time.monotonic()
        ranking = evaluate_ranking_methods(
            evaluation_model, train.unionByName(valid), test, active_users,
            active_movies.select("movieId"), category_map, args, logger, cached,
        )
        logger.info("stage_complete name=ranking_evaluation seconds=%.3f", time.monotonic() - stage_started)

        # Retrain selected configuration on all current valid ratings for publishing.
        stage_started = time.monotonic()
        production_model = als_estimator(args, best_rank, best_iter, best_reg).fit(ratings)
        logger.info("stage_complete name=production_fit seconds=%.3f", time.monotonic() - stage_started)
        if args.model_path:
            production_model.write().save(args.model_path)
        if args.recommendations_path:
            output = fill_and_publish_candidates(
                production_model, ratings, active_users, active_movies, category_map, args, logger
            ).cache()
            cached.append(output)
            output_count = output.count()
            if output_count:
                output.write.mode("errorifexists").parquet(args.recommendations_path)
            else:
                logger.warning("recommendations are empty; no Parquet path created")
        else:
            output_count = 0

        metadata = {
            "run_id": run_id, "batch_id": args.batch_id,
            "started_at_utc": started_at_utc.isoformat(),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": run_id,
            "input": {"source": ("parquet_snapshot" if args.input_snapshot else
                                   "MySQL personalratings joined to user/movieinfo"),
                      "snapshot_path": args.input_snapshot or args.snapshot_path,
                      "snapshot_paths": {
                          "ratings": (args.input_snapshot or args.snapshot_path).rstrip("/\\") + "/ratings",
                          "active_users": (args.input_snapshot or args.snapshot_path).rstrip("/\\") + "/active_users",
                          "active_movies": (args.input_snapshot or args.snapshot_path).rstrip("/\\") + "/active_movies",
                          "movie_categories": (args.input_snapshot or args.snapshot_path).rstrip("/\\") + "/movie_categories",
                      },
                      "rows": quality["trainable_rows"],
                      "quality": quality, "soft_delete_only": True,
                      "cross_table_snapshot_atomic": False,
                      "snapshot_replay": bool(args.input_snapshot),
                      "rating_history_semantics": "current row; rated_at is last update, not immutable history"},
            "temporal_split": {"train_rows": split_sizes[0], "valid_rows": split_sizes[1],
                               "test_rows": split_sizes[2], "train_cutoff_utc": train_cutoff.isoformat(),
                               "valid_cutoff_utc": valid_cutoff.isoformat()},
            "spark_version": SPARK_VERSION,
            "parameters": {"rank_grid": args.rank_grid if args.tune else [args.rank],
                           "iter_grid": args.iter_grid if args.tune else [args.max_iter],
                           "reg_grid": args.reg_grid if args.tune else [args.reg_param],
                           "selected_rank": best_rank, "selected_max_iter": best_iter,
                           "selected_reg_param": best_reg, "implicit_prefs": False,
                           "positive_threshold": args.positive_threshold, "top_n": args.top_n,
                           "candidate_multiplier": args.candidate_multiplier,
                           "model_version": args.model_version,
                           "batch_id": args.batch_id,
                           "seed": args.seed, "als_blocks": args.als_blocks,
                           "checkpoint_interval": args.checkpoint_interval,
                           "checkpoint_dir": checkpoint_dir,
                           "jdbc_partitions": args.jdbc_partitions,
                           "jdbc_fetch_size": args.jdbc_fetch_size,
                           "baseline_pool": args.baseline_pool,
                           "fallback_pool": args.fallback_pool,
                           "shuffle_partitions": args.shuffle_partitions},
            "tuning_results": tuning, "test_regression": test_regression,
            "test_ranking": ranking, "recommendations_rows": output_count,
            "recommendations_path": args.recommendations_path,
            "model_path": args.model_path,
        }
        logger.info("run_summary %s", json.dumps(metadata, sort_keys=True, default=str))
        if args.metadata_path:
            write_json(args.metadata_path, metadata)
            logger.info("metadata_written path=%s", args.metadata_path)
        logger.info("job_complete elapsed_seconds=%.3f", time.monotonic() - started)
        return metadata
    finally:
        for frame in reversed(cached):
            try:
                frame.unpersist(blocking=False)
            except Exception:
                logger.exception("unpersist_failed")
        if spark is not None:
            try:
                spark.stop()
            except Exception:
                logger.exception("spark_stop_failed")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    try:
        run(args)
        return 0
    except Exception:
        LOG.exception("job_failed batch_id=%s", args.batch_id)
        return 1


if __name__ == "__main__":
    sys.exit(main())
