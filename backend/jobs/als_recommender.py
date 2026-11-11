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
    timezones = re.findall(r"(?:[?&])servertimezone=([^&]*)", url, flags=re.IGNORECASE)
    if timezones != ["UTC"]:
        raise ValueError("MYSQL_JDBC_URL must explicitly include serverTimezone=UTC")


def enforce_utc_jdbc_url(url: str) -> str:
    base, separator, query = url.partition("?")
    if not separator:
        return base + "?serverTimezone=UTC"
    parameters = [part for part in query.split("&")
                  if not re.match(r"(?i)^serverTimezone=", part)]
    parameters.append("serverTimezone=UTC")
    return base + "?" + "&".join(parameters)


def find_mysql_connector_jar() -> Path | None:
    configured = os.getenv("MYSQL_CONNECTOR_JAR")
    candidates = ([Path(configured)] if configured else []) + [
        Path.home() / ".m2" / "repository" / "com" / "mysql" /
        "mysql-connector-j" / "8.0.33" / "mysql-connector-j-8.0.33.jar",
    ]
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def jdbc_read(spark: SparkSession, query: str, args, *, partition_column=None, bounds=None) -> DataFrame:
    url = enforce_utc_jdbc_url(os.environ["MYSQL_JDBC_URL"])
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
        F.min("rating").alias("observed_rating_min"),
        F.max("rating").alias("observed_rating_max"),
        F.date_format(F.min("rated_at"), "yyyy-MM-dd HH:mm:ss.SSSSSS").alias("rated_at_min_utc"),
        F.date_format(F.max("rated_at"), "yyyy-MM-dd HH:mm:ss.SSSSSS").alias("rated_at_max_utc"),
    ).first().asDict()

    duplicate_count = (
        ratings.groupBy("userid", "movieid").count()
        .filter(F.col("count") > 1).count()
    )
    quality["duplicate_user_movie_keys"] = duplicate_count
    quality["input_rows"] = raw_count
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
    quality["active_user_count"] = active_users.select("userId").distinct().count()
    quality["active_movie_count"] = active_movies.select("movieId").distinct().count()
    quality["trainable_user_count"] = trainable.select("userId").distinct().count()
    quality["trainable_movie_count"] = trainable.select("movieId").distinct().count()
    freshness_sql = """
      SELECT
        DATE_FORMAT((SELECT MAX(rated_at) FROM personalratings), '%Y-%m-%d %H:%i:%s.%f') AS latest_rating_at,
        DATE_FORMAT((SELECT MAX(updated_at) FROM `user` WHERE deleted_at IS NULL), '%Y-%m-%d %H:%i:%s.%f') AS latest_active_user_update_at,
        DATE_FORMAT((SELECT MAX(updated_at) FROM movieinfo WHERE deleted_at IS NULL), '%Y-%m-%d %H:%i:%s.%f') AS latest_active_movie_update_at,
        DATE_FORMAT((SELECT MAX(generated_at) FROM recommendationitem), '%Y-%m-%d %H:%i:%s.%f') AS latest_recommendation_generated_at
    """
    freshness_row = jdbc_read(spark, freshness_sql, args).first().asDict()
    now_utc = datetime.now(timezone.utc)
    quality["freshness"] = {}
    for key, value in freshness_row.items():
        latest = datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None
        quality["freshness"][key] = {
            "latest_utc": latest.isoformat() if latest else None,
            "age_seconds": (now_utc - latest).total_seconds() if latest else None,
        }
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


def per_user_random_split(ratings: DataFrame, args):
    counts = Window.partitionBy("userId")
    order = Window.partitionBy("userId").orderBy(
        F.xxhash64("userId", "movieId", F.lit(args.seed)), F.asc("movieId")
    )
    ranked = (ratings
              .withColumn("_user_count", F.count("*").over(counts))
              .withColumn("_user_order", F.row_number().over(order))
              .withColumn("_test_count", F.when(F.col("_user_count") >= 3,
                                                  F.greatest(F.lit(1), F.floor(F.col("_user_count") * F.lit(0.1))))
                          .otherwise(F.lit(0)))
              .withColumn("_valid_count", F.when(F.col("_user_count") >= 2,
                                                   F.greatest(F.lit(1), F.floor(F.col("_user_count") * F.lit(0.1))))
                           .otherwise(F.lit(0)))
              .withColumn("_train_count", F.col("_user_count") - F.col("_test_count") - F.col("_valid_count")))
    train = ranked.filter(F.col("_user_order") <= F.col("_train_count")).drop(
        "_user_count", "_user_order", "_test_count", "_valid_count", "_train_count"
    ).cache()
    valid = ranked.filter(
        (F.col("_user_order") > F.col("_train_count"))
        & (F.col("_user_order") <= F.col("_train_count") + F.col("_valid_count"))
    ).drop("_user_count", "_user_order", "_test_count", "_valid_count", "_train_count").cache()
    test = ranked.filter(F.col("_user_order") > F.col("_train_count") + F.col("_valid_count"))\
        .drop("_user_count", "_user_order", "_test_count", "_valid_count", "_train_count").cache()
    sizes = (train.count(), valid.count(), test.count())
    if any(size == 0 for size in sizes):
        for frame in (train, valid, test):
            frame.unpersist()
        raise ValueError(f"Per-user split produced an empty partition: train/valid/test={sizes}")
    return train, valid, test, None, None, sizes


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
              .select("userId", "movieId", "position").cache())
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
    list_sizes = (relevant_users.join(
        ranked.groupBy("userId").agg(F.countDistinct("movieId").alias("list_size")),
        "userId", "left",
    ).fillna({"list_size": 0}))
    list_summary = list_sizes.agg(
        F.avg("list_size").alias("mean_list_size"),
        F.sum((F.col("list_size") < k).cast("long")).alias("short_list_users"),
        F.sum((F.col("list_size") == 0).cast("long")).alias("empty_list_users"),
    ).first().asDict()

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
        "mean_list_size": float(list_summary["mean_list_size"] or 0.0),
        "short_list_users": int(list_summary["short_list_users"] or 0),
        "empty_list_users": int(list_summary["empty_list_users"] or 0),
        "mean_category_coverage_ratio": float(diversity),
        "candidate_policy": "all active catalog items with model item factors scored for every warm evaluation user; exclude train-seen",
    }
    logger.info("ranking_metrics %s", json.dumps({"dataset": label, "k": k, **result}, sort_keys=True))
    ranked.unpersist(blocking=False)
    return result


def score_full_candidate_catalog(model, train: DataFrame, heldout: DataFrame,
                                 catalog: DataFrame, args, *, sample_users: int | None = None):
    candidate_catalog = (catalog.select("movieId").distinct()
                         .join(model.itemFactors.select(F.col("id").alias("movieId")), "movieId", "inner")
                         .distinct().cache())
    factor_users = model.userFactors.select(F.col("id").alias("userId"))
    relevant_users = (heldout.filter(F.col("rating") >= args.positive_threshold)
                      .select("userId").distinct().join(factor_users, "userId", "inner"))
    if sample_users:
        relevant_users = (relevant_users
                          .withColumn("_sample_key", F.xxhash64("userId", F.lit(args.seed)))
                          .orderBy("_sample_key").limit(sample_users).drop("_sample_key"))
    relevant_users = relevant_users.cache()
    users_count = relevant_users.count()
    item_count = candidate_catalog.count()
    if users_count == 0 or item_count == 0:
        candidate_catalog.unpersist()
        relevant_users.unpersist()
        raise ValueError("Ranking evaluation has no warm relevant users or factorized catalog items")
    pair_count = users_count * item_count
    if pair_count > args.max_ranking_pairs:
        candidate_catalog.unpersist()
        relevant_users.unpersist()
        raise ValueError(
            f"Exact ranking candidate set is too large ({pair_count} user-item pairs; "
            f"limit={args.max_ranking_pairs}); reduce --ranking-user-sample or raise --max-ranking-pairs"
        )

    relevant = (heldout.filter(F.col("rating") >= args.positive_threshold)
                .join(relevant_users, "userId", "inner")
                .select("userId", "movieId").distinct().cache())
    if relevant.limit(1).count() == 0:
        for frame in (candidate_catalog, relevant_users, relevant):
            frame.unpersist()
        raise ValueError("No relevant warm-user interactions at positive threshold")

    seen = train.select("userId", "movieId").distinct()
    pairs = (relevant_users.crossJoin(candidate_catalog)
             .join(seen, ["userId", "movieId"], "left_anti"))
    predictions = model.transform(pairs).select("userId", "movieId", F.col("prediction").alias("als_score"))
    item_stats = train.groupBy("movieId").agg(
        F.count("*").alias("rating_count"), F.avg("rating").alias("mean_rating")
    )
    global_mean = train.agg(F.avg("rating").alias("global_mean")).first()["global_mean"]
    popularity = (candidate_catalog.join(item_stats, "movieId", "left")
                  .fillna({"rating_count": 0, "mean_rating": float(global_mean)})
                  .withColumn("popularity_score", F.col("rating_count") * F.col("mean_rating"))
                  .withColumn("bayes_score",
                              (F.col("rating_count") * F.col("mean_rating")
                               + F.lit(args.bayes_prior_strength) * F.lit(float(global_mean)))
                              / (F.col("rating_count") + F.lit(args.bayes_prior_strength)))
                  .select("movieId", "popularity_score", "bayes_score"))
    scored = (predictions.join(popularity, "movieId", "left")
              .filter(F.col("als_score").isNotNull() & ~F.isnan("als_score"))
              .cache())
    return candidate_catalog, relevant_users, relevant, scored, pair_count


def rank_scored_candidates(scored: DataFrame, score_column: str, k: int) -> DataFrame:
    window = Window.partitionBy("userId").orderBy(F.desc(score_column), F.asc("movieId"))
    return (scored.withColumn("position", F.row_number().over(window))
            .filter(F.col("position") <= k)
            .select("userId", "movieId", "position"))


def evaluate_ranking_methods(model, train: DataFrame, heldout: DataFrame, all_active_users: DataFrame,
                             catalog: DataFrame, category_map: DataFrame, args, logger,
                             cache_registry: list[DataFrame], *, methods=None,
                             sample_users: int | None = None, hybrid_weights=None,
                             label_prefix="test") -> dict:
    candidate_catalog, eval_users, relevant, scored, pair_count = score_full_candidate_catalog(
        model, train, heldout, catalog, args, sample_users=sample_users
    )
    cached_scored = scored
    if hybrid_weights is not None:
        weights = hybrid_weights
    elif "hybrid" in (methods or ()):
        weights = [args.selected_hybrid_weight]
    else:
        weights = []
    scored = (scored
              .withColumn("als_percentile", F.percent_rank().over(
                  Window.partitionBy("userId").orderBy(F.asc("als_score"))))
              .withColumn("popularity_percentile", F.percent_rank().over(
                  Window.partitionBy("userId").orderBy(F.asc("popularity_score"))))
              .withColumn("bayes_percentile", F.percent_rank().over(
                  Window.partitionBy("userId").orderBy(F.asc("bayes_score")))))
    score_columns = {
        "als": "als_score",
        "popularity": "popularity_score",
        "bayesian": "bayes_score",
    }
    results = {}
    for method in methods or ("als", "popularity", "bayesian", "random"):
        if method in score_columns:
            ranked = rank_scored_candidates(scored, score_columns[method], args.top_n)
            results[method] = topk_metrics(
                ranked, relevant, candidate_catalog, category_map, all_active_users,
                args.top_n, logger, f"{label_prefix}_{method}",
            )
        elif method == "random":
            random_scored = scored.withColumn(
                "random_score", F.xxhash64("userId", "movieId", F.lit(args.seed))
            )
            ranked = rank_scored_candidates(random_scored, "random_score", args.top_n)
            results[method] = topk_metrics(
                ranked, relevant, candidate_catalog, category_map, all_active_users,
                args.top_n, logger, f"{label_prefix}_random",
            )
        elif method == "hybrid":
            for weight in weights:
                hybrid = scored.withColumn(
                    "hybrid_score",
                    F.lit(1.0 - weight) * F.col("als_percentile")
                    + F.lit(weight) * F.col("popularity_percentile"),
                )
                ranked = rank_scored_candidates(hybrid, "hybrid_score", args.top_n)
                results[f"hybrid_pop_{weight:g}"] = topk_metrics(
                    ranked, relevant, candidate_catalog, category_map, all_active_users,
                    args.top_n, logger, f"{label_prefix}_hybrid_pop_{weight:g}",
                )
        else:
            raise ValueError(f"Unknown ranking method: {method}")

    positive_items = relevant.select("movieId").distinct()
    factor_positive_count = positive_items.join(candidate_catalog, "movieId", "inner").count()
    positive_count = positive_items.count()
    results["evaluation_scope"] = {
        "evaluated_users": eval_users.count(),
        "candidate_items": candidate_catalog.count(),
        "candidate_pairs_before_seen_filter": pair_count,
        "model_scored_user_item_pairs": scored.count(),
        "positive_items_with_factors": factor_positive_count,
        "positive_item_factor_coverage": factor_positive_count / positive_count if positive_count else 0.0,
        "positive_threshold": args.positive_threshold,
        "candidate_policy": "exact full factorized active catalog per warm user; remove train-seen items before ranking",
    }
    for frame in (cached_scored, candidate_catalog, eval_users, relevant):
        frame.unpersist(blocking=False)
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
                      .join(catalog, "movieId", "inner")
                      .select("userId", "movieId", F.col("score").alias("als_score")))
    # The verified validation blend is used for warm users. The bounded hot
    # pool supplies cold users and fills gaps after seen/deleted items are removed.
    hot_candidates = (active_users.crossJoin(F.broadcast(hot_pool))
                      .join(seen, ["userId", "movieId"], "left_anti")
                      .join(catalog, "movieId", "inner")
                      .select("userId", "movieId", F.col("score").alias("pop_score")))
    candidates = als_candidates.join(hot_candidates, ["userId", "movieId"], "full_outer")
    candidate_window = Window.partitionBy("userId")
    candidates = (candidates
                  .withColumn("als_pct", F.percent_rank().over(
                      candidate_window.orderBy(F.asc_nulls_first("als_score"))))
                  .withColumn("pop_pct", F.percent_rank().over(
                      candidate_window.orderBy(F.asc_nulls_first("pop_score"))))
                  .withColumn("score", F.when(F.col("als_score").isNull(), F.col("pop_pct"))
                              .otherwise((F.lit(1.0 - args.selected_hybrid_weight) * F.col("als_pct"))
                                         + (F.lit(args.selected_hybrid_weight) * F.coalesce(F.col("pop_pct"), F.lit(0.0)))))
                  .withColumn("source", F.when(F.col("als_score").isNull(), F.lit("popular_fallback"))
                              .otherwise(F.lit("als_hybrid"))))
    rank_window = Window.partitionBy("userId").orderBy(F.desc("score"), F.asc("movieId"))
    ranked = (candidates.withColumn("position", F.row_number().over(rank_window))
              .filter(F.col("position") <= args.top_n)
              .select("userId", "movieId", "score", "source", "position"))
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
    duplicate_output = result.groupBy("request_id", "movieid").count().filter(F.col("count") > 1).limit(1).count()
    if duplicate_output:
        raise ValueError("Generated recommendations contain duplicate (request_id,movieid) keys")
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


def tune_parameters(train: DataFrame, valid: DataFrame, all_active_users: DataFrame,
                    catalog: DataFrame, category_map: DataFrame, args, logger,
                    cache_registry: list[DataFrame]) -> tuple[int, int, float, list[dict]]:
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
                ranking = evaluate_ranking_methods(
                    model, train, valid, all_active_users, catalog, category_map,
                    args, logger, cache_registry, methods=("als",),
                    sample_users=args.ranking_user_sample,
                    label_prefix=f"validation_r{rank}_i{iters}_reg{reg}",
                )
                row = {"rank": rank, "max_iter": iters, "reg_param": reg,
                       "validation_rmse": metrics["rmse"], "validation_mae": metrics["mae"],
                       "validation_coverage": metrics["prediction_coverage"],
                       "validation_ndcg_at_k": ranking["als"]["ndcg_at_k"],
                       "validation_precision_at_k": ranking["als"]["precision_at_k"],
                       "fit_eval_seconds": time.monotonic() - started}
                grid_results.append(row)
                logger.info("tuning_candidate %s", json.dumps(row, sort_keys=True))
    best = max(grid_results, key=lambda row: (
        row["validation_ndcg_at_k"], -row["validation_rmse"], -row["rank"],
    ))
    return best["rank"], best["max_iter"], best["reg_param"], grid_results


def select_hybrid_weight(model, train: DataFrame, valid: DataFrame,
                         all_active_users: DataFrame, catalog: DataFrame,
                         category_map: DataFrame, args, logger,
                         cache_registry: list[DataFrame]) -> tuple[float, dict]:
    weights = parse_grid(args.hybrid_popularity_weights, float)
    if any(weight < 0 or weight > 1 for weight in weights):
        raise ValueError("hybrid popularity weights must be in [0, 1]")
    metrics = evaluate_ranking_methods(
        model, train, valid, all_active_users, catalog, category_map,
        args, logger, cache_registry, methods=("als", "hybrid"),
        sample_users=args.ranking_user_sample, hybrid_weights=weights,
        label_prefix="validation_blend",
    )
    selected = max(weights, key=lambda weight: (
        metrics[f"hybrid_pop_{weight:g}"]["ndcg_at_k"], -weight,
    ))
    return selected, metrics


def write_json(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)


def export_user_recommendations_jsonl(frame: DataFrame, root: str, batch_id: str) -> str:
    """Publish immutable per-user JSONL files without Hadoop's local filesystem."""
    publish_root = Path(root).resolve()
    batch_root = publish_root / "batches" / batch_id
    users_root = batch_root / "users"
    users_root.mkdir(parents=True, exist_ok=False)
    columns = (
        "userid", "movieid", "position", "prediction_score",
        "movie_rating_snapshot", "algorithm_version", "generated_at",
    )
    required = set(columns)
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Recommendation output missing JSONL columns: {sorted(missing)}")

    current_user = None
    current_rows = []

    def flush_user(user_id, rows):
        if user_id is None:
            return
        path = users_root / f"{user_id}.jsonl"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            for item in rows:
                stream.write(json.dumps(item, sort_keys=True, default=str) + "\n")

    for row in frame.select(*columns).orderBy("userid", "position").toLocalIterator():
        item = row.asDict(recursive=True)
        user_id = int(item["userid"])
        if current_user is not None and user_id != current_user:
            flush_user(current_user, current_rows)
            current_rows = []
        current_user = user_id
        current_rows.append(item)
    flush_user(current_user, current_rows)

    pointer = {"batch_id": batch_id, "users_dir": str(users_root), "format": "jsonl-v1"}
    publish_root.mkdir(parents=True, exist_ok=True)
    pointer_tmp = publish_root / f"latest.{batch_id}.tmp"
    with pointer_tmp.open("x", encoding="utf-8") as stream:
        json.dump(pointer, stream, sort_keys=True)
    os.replace(pointer_tmp, publish_root / "latest.json")
    return str(batch_root)


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
    parser.add_argument("--bayes-prior-strength", type=float, default=10.0)
    parser.add_argument("--hybrid-popularity-weights", default="0,0.1,0.25,0.5,0.75,1")
    parser.add_argument("--ranking-user-sample", type=int, default=1000)
    parser.add_argument("--max-ranking-pairs", type=int, default=25000000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--als-blocks", type=int, default=10)
    parser.add_argument("--checkpoint-interval", type=int, default=10)
    parser.add_argument("--checkpoint-dir", default=os.getenv("ALS_CHECKPOINT_DIR"))
    parser.add_argument("--jdbc-partitions", type=int, default=int(os.getenv("MYSQL_JDBC_PARTITIONS", "1")))
    parser.add_argument("--jdbc-fetch-size", type=int, default=int(os.getenv("MYSQL_FETCH_SIZE", "10000")))
    parser.add_argument("--shuffle-partitions", type=int, default=int(os.getenv("SPARK_SHUFFLE_PARTITIONS", "200")))
    parser.add_argument("--train-cutoff", default=os.getenv("ALS_TRAIN_CUTOFF"))
    parser.add_argument("--valid-cutoff", default=os.getenv("ALS_VALID_CUTOFF"))
    parser.add_argument("--split-mode", choices=("per_user_random", "rated_at"),
                        default=os.getenv("ALS_SPLIT_MODE", "per_user_random"))
    parser.add_argument("--model-version", default="als-explicit-v1")
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--snapshot-path", default=os.getenv("ALS_SNAPSHOT_PATH"))
    parser.add_argument("--input-snapshot", default=os.getenv("ALS_INPUT_SNAPSHOT"))
    parser.add_argument("--no-snapshot", action="store_true",
                        help="run an ephemeral MySQL-backed evaluation without persisting a data snapshot")
    parser.add_argument("--recommendations-path", default=None)
    parser.add_argument("--jsonl-recommendations-root", default=os.getenv("ALS_RECOMMENDATION_ROOT"),
                        help="publish immutable per-user JSONL files and atomically update latest.json")
    parser.add_argument("--validate-recommendations", action="store_true",
                        help="generate and validate Top-N recommendations without writing Parquet")
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
    snapshot_modes = int(bool(args.snapshot_path)) + int(bool(args.input_snapshot)) + int(args.no_snapshot)
    if snapshot_modes != 1:
        raise ValueError("provide exactly one of --snapshot-path, --input-snapshot, or --no-snapshot")
    if min(args.rank, args.max_iter, args.top_n, args.positive_threshold,
           args.candidate_multiplier, args.baseline_pool, args.fallback_pool,
           args.ranking_user_sample, args.max_ranking_pairs,
           args.jdbc_partitions, args.jdbc_fetch_size, args.shuffle_partitions,
           args.als_blocks) <= 0:
        raise ValueError("all count, partition, rank, and iteration parameters must be positive")
    if args.bayes_prior_strength <= 0:
        raise ValueError("bayes prior strength must be positive")
    if not 1 <= args.positive_threshold <= 5:
        raise ValueError("positive threshold must be within the 1-5 rating range")
    if args.checkpoint_interval == 0 or args.checkpoint_interval < -1:
        raise ValueError("checkpoint interval must be positive or -1 to disable checkpointing")
    if not args.input_snapshot:
        os.environ["MYSQL_JDBC_URL"] = enforce_utc_jdbc_url(os.environ["MYSQL_JDBC_URL"])
        validate_jdbc_url(os.environ["MYSQL_JDBC_URL"])

    started = time.monotonic()
    started_at_utc = datetime.now(timezone.utc)
    spark = None
    cached = []
    jsonl_recommendations_path = None
    try:
        logger.info("job_start batch_id=%s spark_runtime=%s", args.batch_id, SPARK_VERSION)
        builder = (SparkSession.builder.appName("movie-als-recommender")
                   .config("spark.sql.session.timeZone", "UTC")
                   .config("spark.sql.shuffle.partitions", str(args.shuffle_partitions)))
        spark_master = os.getenv("SPARK_MASTER")
        if spark_master:
            builder = builder.master(spark_master)
        if not args.input_snapshot:
            connector_jar = find_mysql_connector_jar()
            if connector_jar is None:
                raise FileNotFoundError(
                    "MySQL Connector/J jar not found; set MYSQL_CONNECTOR_JAR to its local path"
                )
            # A local classpath avoids Spark's Windows jar-distribution chmod path.
            builder = (builder.config("spark.driver.extraClassPath", str(connector_jar))
                       .config("spark.executor.extraClassPath", str(connector_jar)))
        spark = builder.getOrCreate()
        checkpoint_dir = args.checkpoint_dir
        if args.checkpoint_interval > 0:
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
        if args.split_mode == "per_user_random":
            train, valid, test, train_cutoff, valid_cutoff, split_sizes = per_user_random_split(ratings, args)
        else:
            train, valid, test, train_cutoff, valid_cutoff, split_sizes = temporal_split(ratings, args)
        cached.extend([train, valid, test])
        logger.info("temporal_split %s", json.dumps({
            "mode": args.split_mode,
            "train_rows": split_sizes[0], "valid_rows": split_sizes[1], "test_rows": split_sizes[2],
            "train_cutoff_utc": train_cutoff.isoformat() if train_cutoff else None,
            "valid_cutoff_utc": valid_cutoff.isoformat() if valid_cutoff else None,
            "semantics": ("deterministic per-user holdout of current ratings; not a future-event backtest"
                          if args.split_mode == "per_user_random" else
                          "rated_at is current-rating update time; not immutable rating history"),
        }, sort_keys=True))
        logger.info("stage_complete name=temporal_split seconds=%.3f", time.monotonic() - stage_started)

        stage_started = time.monotonic()
        if not args.input_snapshot:
            cached.extend([active_users, active_movies, category_map])
        best_rank, best_iter, best_reg, tuning = tune_parameters(
            train, valid, active_users, active_movies.select("movieId"), category_map,
            args, logger, cached,
        )
        logger.info("stage_complete name=tune seconds=%.3f", time.monotonic() - stage_started)
        stage_started = time.monotonic()
        validation_model = als_estimator(args, best_rank, best_iter, best_reg).fit(train)
        args.selected_hybrid_weight, validation_blend = select_hybrid_weight(
            validation_model, train, valid, active_users, active_movies.select("movieId"),
            category_map, args, logger, cached,
        )
        logger.info("selected_hybrid_weight value=%s", args.selected_hybrid_weight)
        logger.info("stage_complete name=validation_blend seconds=%.3f", time.monotonic() - stage_started)
        stage_started = time.monotonic()
        evaluation_model = als_estimator(args, best_rank, best_iter, best_reg).fit(train.unionByName(valid))
        test_regression = regression_metrics(evaluation_model, test, logger, "test_holdout")
        logger.info("stage_complete name=test_evaluation seconds=%.3f", time.monotonic() - stage_started)

        stage_started = time.monotonic()
        ranking = evaluate_ranking_methods(
            evaluation_model, train.unionByName(valid), test, active_users,
            active_movies.select("movieId"), category_map, args, logger, cached,
            methods=("als", "popularity", "bayesian", "random", "hybrid"),
            sample_users=args.ranking_user_sample,
            label_prefix="test",
        )
        logger.info("stage_complete name=ranking_evaluation seconds=%.3f", time.monotonic() - stage_started)

        # Retrain selected configuration on all current valid ratings for publishing.
        stage_started = time.monotonic()
        production_model = als_estimator(args, best_rank, best_iter, best_reg).fit(ratings)
        logger.info("stage_complete name=production_fit seconds=%.3f", time.monotonic() - stage_started)
        if args.model_path:
            production_model.write().save(args.model_path)
        if args.recommendations_path or args.jsonl_recommendations_root or args.validate_recommendations:
            output = fill_and_publish_candidates(
                production_model, ratings, active_users, active_movies, category_map, args, logger
            ).cache()
            cached.append(output)
            output_count = output.count()
            invalid_position_count = output.filter(
                (F.col("position") < 1) | (F.col("position") > args.top_n)
            ).count()
            duplicate_key_count = (output.groupBy("request_id", "movieid").count()
                                   .filter(F.col("count") > 1).count())
            duplicate_position_count = (output.groupBy("request_id", "position").count()
                                        .filter(F.col("count") > 1).count())
            missing_user_count = (output.select(F.col("userid").alias("userId")).distinct()
                                  .join(active_users.select("userId").distinct(), "userId", "left_anti").count())
            missing_movie_count = (output.select(F.col("movieid").alias("movieId")).distinct()
                                   .join(active_movies.select("movieId").distinct(), "movieId", "left_anti").count())
            seen_recommendation_count = (output.select(F.col("userid").alias("userId"),
                                                       F.col("movieid").alias("movieId"))
                                         .join(ratings.select("userId", "movieId").distinct(),
                                               ["userId", "movieId"], "inner").count())
            output_validation = {
                "rows": output_count,
                "invalid_position_rows": invalid_position_count,
                "duplicate_request_movie_keys": duplicate_key_count,
                "duplicate_request_positions": duplicate_position_count,
                "missing_active_users": missing_user_count,
                "missing_active_movies": missing_movie_count,
                "already_rated_recommendations": seen_recommendation_count,
                "schema": output.schema.jsonValue(),
            }
            logger.info("recommendation_output_validation %s",
                        json.dumps(output_validation, sort_keys=True, default=str))
            if any(output_validation[key] for key in (
                "invalid_position_rows", "duplicate_request_movie_keys", "missing_active_users",
                "duplicate_request_positions", "missing_active_movies", "already_rated_recommendations",
            )):
                raise ValueError("Generated recommendations failed output integrity checks")
            if output_count:
                if args.recommendations_path:
                    output.write.mode("errorifexists").parquet(args.recommendations_path)
                if args.jsonl_recommendations_root:
                    # Release the validation cache before toLocalIterator streams
                    # rows; this avoids stale cached SparkPlan sessions on Windows.
                    output.unpersist(blocking=True)
                    published_path = export_user_recommendations_jsonl(
                        output, args.jsonl_recommendations_root, args.batch_id
                    )
                    jsonl_recommendations_path = published_path
                    logger.info("recommendations_jsonl_published path=%s rows=%s",
                                published_path, output_count)
                if args.validate_recommendations and not args.recommendations_path \
                        and not args.jsonl_recommendations_root:
                    logger.info("recommendations validated in memory; no Parquet output requested")
            else:
                logger.warning("recommendations are empty; no Parquet path created")
        else:
            output_count = 0
            output_validation = None

        metadata = {
            "run_id": run_id, "batch_id": args.batch_id,
            "started_at_utc": started_at_utc.isoformat(),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": None if args.no_snapshot else run_id,
            "input": {"source": ("mysql_ephemeral_no_snapshot" if args.no_snapshot else
                                   "parquet_snapshot" if args.input_snapshot else
                                   "MySQL personalratings joined to user/movieinfo"),
                      "snapshot_path": None if args.no_snapshot else (args.input_snapshot or args.snapshot_path),
                      "snapshot_paths": None if args.no_snapshot else {
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
            "data_split": {"mode": args.split_mode, "train_rows": split_sizes[0], "valid_rows": split_sizes[1],
                            "test_rows": split_sizes[2],
                            "train_cutoff_utc": train_cutoff.isoformat() if train_cutoff else None,
                            "valid_cutoff_utc": valid_cutoff.isoformat() if valid_cutoff else None,
                            "semantics": ("deterministic per-user holdout of current ratings; not a future-event backtest"
                                          if args.split_mode == "per_user_random" else
                                          "rated_at is current-rating update time; not immutable rating history")},
            "spark_version": SPARK_VERSION,
            "parameters": {"rank_grid": args.rank_grid if args.tune else [args.rank],
                           "iter_grid": args.iter_grid if args.tune else [args.max_iter],
                           "reg_grid": args.reg_grid if args.tune else [args.reg_param],
                           "selected_rank": best_rank, "selected_max_iter": best_iter,
                           "selected_reg_param": best_reg, "implicit_prefs": False,
                            "selected_hybrid_popularity_weight": args.selected_hybrid_weight,
                            "hybrid_popularity_weights": args.hybrid_popularity_weights,
                            "bayes_prior_strength": args.bayes_prior_strength,
                            "ranking_user_sample": args.ranking_user_sample,
                            "max_ranking_pairs": args.max_ranking_pairs,
                            "split_mode": args.split_mode,
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
            "tuning_results": tuning, "validation_blend": validation_blend,
            "test_regression": test_regression,
            "test_ranking": ranking, "recommendations_rows": output_count,
            "recommendation_output_validation": output_validation,
            "recommendations_path": args.recommendations_path,
            "jsonl_recommendations_path": jsonl_recommendations_path,
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
