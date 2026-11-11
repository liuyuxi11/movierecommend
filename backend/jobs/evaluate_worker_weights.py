"""Read-only validation of the online recommendation reranking weights."""

from __future__ import annotations

import argparse
import json
import logging
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

from dotenv import dotenv_values
from pyspark.sql import SparkSession, Window, functions as F

import als_recommender as als


WEIGHT_CONFIGS = {
    "current_0.75_0.10_0.15": (0.75, 0.10, 0.15),
    "offline_only": (1.0, 0.0, 0.0),
    "popularity_only": (0.0, 1.0, 0.0),
    "profile_only": (0.0, 0.0, 1.0),
    "equal_weights": (1 / 3, 1 / 3, 1 / 3),
    "offline_pop_0.85_0.15": (0.85, 0.15, 0.0),
    "offline_profile_0.83_0.17": (0.83, 0.0, 0.17),
    "more_profile_0.65_0.10_0.25": (0.65, 0.10, 0.25),
    "less_profile_0.80_0.10_0.10": (0.80, 0.10, 0.10),
}


def load_project_env() -> None:
    for key, value in dotenv_values(Path(__file__).resolve().parents[2] / ".env").items():
        if value is not None:
            os.environ.setdefault(key, value)


def build_args(sample_users: int, seed: int) -> SimpleNamespace:
    return SimpleNamespace(
        input_snapshot=None, snapshot_path=None, no_snapshot=True,
        jdbc_partitions=1, jdbc_fetch_size=10000,
        seed=seed, rank=32, max_iter=8, reg_param=0.05,
        checkpoint_interval=-1, als_blocks=10, top_n=20,
        candidate_multiplier=5, fallback_pool=500, batch_id=uuid.uuid4().hex[:20],
        model_version="worker-weight-validation", selected_hybrid_weight=0.75,
        ranking_user_sample=sample_users, max_ranking_pairs=25000000,
        positive_threshold=4, shuffle_partitions=32,
    )


def find_mysql_connector() -> Path:
    configured = os.getenv("MYSQL_CONNECTOR_JAR")
    candidates = ([Path(configured)] if configured else []) + [
        Path.home() / ".m2" / "repository" / "com" / "mysql" /
        "mysql-connector-j" / "8.0.33" / "mysql-connector-j-8.0.33.jar",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "MySQL Connector/J jar is missing; set MYSQL_CONNECTOR_JAR to its local path"
    )


def run(sample_users: int, seed: int, output: Path) -> dict:
    load_project_env()
    als.configure_logging("INFO")
    args = build_args(sample_users, seed)
    os.environ["MYSQL_JDBC_URL"] = als.enforce_utc_jdbc_url(os.environ["MYSQL_JDBC_URL"])
    als.validate_jdbc_url(os.environ["MYSQL_JDBC_URL"])

    spark = None
    cached = []
    try:
        connector_jar = find_mysql_connector()
        spark = (SparkSession.builder.appName("worker-rerank-weight-validation")
                 .config("spark.sql.session.timeZone", "UTC")
                 .config("spark.sql.shuffle.partitions", str(args.shuffle_partitions))
                 .config("spark.driver.extraClassPath", str(connector_jar))
                 .config("spark.executor.extraClassPath", str(connector_jar))
                 .getOrCreate())
        raw, ratings, active_users, active_movies, category_map, quality = als.extract_database_snapshot(spark, args)
        cached.extend([raw, ratings, active_users, active_movies, category_map])
        if quality["duplicate_user_movie_keys"]:
            raise ValueError("Duplicate (userid,movieid) rows make this validation nondeterministic")

        train, valid, test, _, _, split_sizes = als.per_user_random_split(ratings, args)
        cached.extend([train, valid, test])
        train_validation = train.unionByName(valid).cache()
        cached.append(train_validation)

        test_positives = test.filter(F.col("rating") >= args.positive_threshold)
        warm_users = train_validation.select("userId").distinct()
        sample = (test_positives.select("userId").distinct().join(warm_users, "userId")
                  .withColumn("_sample_key", F.xxhash64("userId", F.lit(seed)))
                  .orderBy("_sample_key", "userId").limit(sample_users)
                  .select("userId").cache())
        cached.append(sample)
        sample_count = sample.count()
        if sample_count == 0:
            raise ValueError("No warm validation users have positive held-out ratings")

        model = als.als_estimator(args, args.rank, args.max_iter, args.reg_param).fit(train_validation)
        offline = als.fill_and_publish_candidates(
            model, train_validation, sample, active_movies, category_map, args,
            logging.LoggerAdapter(logging.getLogger("worker_weight_validation"), {}),
        ).select(
            F.col("userid").alias("userId"), F.col("movieid").alias("movieId"),
            F.col("position").cast("int").alias("offline_position"),
        ).cache()
        cached.append(offline)

        movie_features = als.jdbc_read(
            spark,
            "SELECT movieid AS movieId, typelist, averating, numrating "
            "FROM movieinfo WHERE deleted_at IS NULL",
            args,
        ).select(
            F.col("movieId").cast("int"), "typelist",
            F.col("averating").cast("double").alias("averating"),
            F.col("numrating").cast("long").alias("numrating"),
        ).cache()
        cached.append(movie_features)

        hot_order = Window.orderBy(F.desc_nulls_last("averating"),
                                   F.desc_nulls_last("numrating"), F.asc("movieId"))
        hot_pool = (movie_features.withColumn("hot_position", F.row_number().over(hot_order))
                    .filter(F.col("hot_position") <= 100).select("movieId", "hot_position")
                    .withColumn("popularity_score",
                                F.lit(1.0) - (F.col("hot_position") - 1) / F.lit(99.0)))
        seen = train_validation.select("userId", "movieId").distinct()
        hot_candidates = (sample.crossJoin(F.broadcast(hot_pool))
                          .join(seen, ["userId", "movieId"], "left_anti"))
        candidates = (offline.join(hot_candidates, ["userId", "movieId"], "full_outer")
                      .join(movie_features.select("movieId", "typelist"), "movieId", "left")
                      .cache())
        cached.append(candidates)

        # Worker profile preferences use current, already observed user ratings.
        item_genres = (movie_features.select("movieId", F.explode_outer(
            F.split(F.coalesce(F.col("typelist"), F.lit("")), ",")
        ).alias("genre")).withColumn("genre", F.lower(F.trim("genre")))
            .filter(F.col("genre") != "").distinct().cache())
        cached.append(item_genres)
        genre_preferences = (train_validation.join(sample, "userId")
                             .join(item_genres.select("movieId", "genre"), "movieId")
                             .groupBy("userId", "genre")
                             .agg(F.avg((F.col("rating") - F.lit(1.0)) / F.lit(4.0))
                                  .alias("genre_preference")))
        candidate_genres = (candidates.select("userId", "movieId", "typelist")
                            .withColumn("genre", F.explode_outer(
                                F.split(F.coalesce(F.col("typelist"), F.lit("")), ",")
                            )).withColumn("genre", F.lower(F.trim("genre")))
                            .filter(F.col("genre") != "").distinct())
        profile = (candidate_genres.join(genre_preferences, ["userId", "genre"], "inner")
                   .groupBy("userId", "movieId")
                   .agg(F.avg("genre_preference").alias("profile_score")))
        offline_sizes = offline.groupBy("userId").agg(F.count("*").alias("offline_count"))
        scored = (candidates.join(offline_sizes, "userId", "left")
                  .join(profile, ["userId", "movieId"], "left")
                  .withColumn("offline_score", F.when(
                      F.col("offline_position").isNotNull(),
                      F.lit(1.0) - (F.col("offline_position") - 1) /
                      F.greatest(F.coalesce(F.col("offline_count"), F.lit(1)), F.lit(1)),
                  )))

        relevant = (test_positives.join(sample, "userId")
                    .select("userId", "movieId").distinct().cache())
        cached.append(relevant)
        catalog = active_movies.select("movieId").distinct()
        metrics = {}
        for name, (offline_weight, popularity_weight, profile_weight) in WEIGHT_CONFIGS.items():
            active = []
            if offline_weight > 0:
                active.append((offline_weight, "offline_score"))
            if popularity_weight > 0:
                active.append((popularity_weight, "popularity_score"))
            if profile_weight > 0:
                active.append((profile_weight, "profile_score"))
            numerator = sum((F.lit(weight) * F.coalesce(F.col(column), F.lit(0.0))
                             for weight, column in active), F.lit(0.0))
            denominator = sum((F.when(F.col(column).isNotNull(), F.lit(weight))
                               .otherwise(F.lit(0.0)) for weight, column in active), F.lit(0.0))
            fallback_score = F.coalesce("popularity_score", "profile_score", "offline_score", F.lit(0.0))
            ranked = (scored.withColumn("score", F.when(denominator > 0, numerator / denominator)
                                        .otherwise(fallback_score))
                      .withColumn("position", F.row_number().over(
                          Window.partitionBy("userId").orderBy(F.desc("score"), F.asc("movieId"))))
                      .filter(F.col("position") <= args.top_n)
                      .select("userId", "movieId", "position"))
            result = als.topk_metrics(
                ranked, relevant, catalog, category_map, sample, args.top_n,
                logging.getLogger("worker_weight_validation"), name,
            )
            result["candidate_policy"] = (
                "per-user offline Top-20 union active MovieInfo popularity Top-100; "
                "exclude train+validation-seen movies"
            )
            result["weights"] = {"offline": offline_weight, "popularity": popularity_weight,
                                 "profile": profile_weight}
            metrics[name] = result

        return {
            "evaluation": {
                "source": "movierecommend_test.personalratings (read-only)",
                "input_rows": quality["trainable_rows"], "split": "per_user_random",
                "seed": seed, "train_rows": split_sizes[0], "valid_rows": split_sizes[1],
                "test_rows": split_sizes[2], "positive_threshold": args.positive_threshold,
                "top_k": args.top_n, "sampled_warm_positive_users": sample_count,
                "candidate_policy": "offline pipeline Top-20 union Worker MovieInfo top-100, exclude train+valid-seen",
                "als": {"rank": args.rank, "max_iter": args.max_iter,
                        "reg_param": args.reg_param, "implicit_prefs": False},
                "profile_source": "typelist joined to train+validation ratings",
                "popularity_source": "active MovieInfo averating/numrating (same serving source)",
                "note": "MovieInfo popularity fields may include ratings outside personalratings; interpret as serving-feature evaluation, not a pure interaction-only backtest.",
            },
            "weight_results": metrics,
        }
    finally:
        for frame in reversed(cached):
            try:
                frame.unpersist(blocking=False)
            except Exception:
                pass
        if spark is not None:
            spark.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-users", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.sample_users <= 0:
        parser.error("--sample-users must be positive")
    result = run(args.sample_users, args.seed, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps({"output": str(args.output.resolve()),
                      "sampled_users": result["evaluation"]["sampled_warm_positive_users"],
                      "weights_evaluated": len(result["weight_results"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
