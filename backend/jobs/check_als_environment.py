"""Fail-fast checks for the Spark ALS runtime without displaying credentials."""

import os
import re
import shutil
import subprocess
import sys
import argparse
from pathlib import Path
from urllib.parse import urlsplit

try:
    import pyspark
except ImportError:
    print("ERROR: pyspark is not installed")
    raise SystemExit(1)

java = shutil.which("java")
spark_submit = shutil.which("spark-submit")
if not spark_submit:
    suffix = ".cmd" if os.name == "nt" else ""
    candidate = Path(sys.executable).parent / f"spark-submit{suffix}"
    spark_submit = str(candidate) if candidate.is_file() else None
if java:
    version_result = subprocess.run([java, "-version"], capture_output=True, text=True, check=False)
    version_text = version_result.stderr + version_result.stdout
    version_match = re.search(r'version "(\d+)', version_text)
    java_major = int(version_match.group(1)) if version_match else None
else:
    java_major = None
print(f"pyspark_version={pyspark.__version__}")
print(f"java_executable_found={bool(java)}")
print(f"java_major={java_major}")
print(f"spark_submit_found={bool(spark_submit)}")
if not java or not spark_submit or java_major not in (17, 21):
    print("ERROR: use a Spark-compatible Java 17 or 21 runtime")
    raise SystemExit(1)

parser = argparse.ArgumentParser()
parser.add_argument("--probe-mysql", action="store_true")
args = parser.parse_args()
if args.probe_mysql:
    url = os.getenv("MYSQL_JDBC_URL", "")
    if not url.startswith("jdbc:mysql://"):
        print("ERROR: MYSQL_JDBC_URL must use jdbc:mysql://")
        raise SystemExit(1)
    if not re.search(r"(?:[?&])serverTimezone=UTC(?:&|$)", url, re.IGNORECASE):
        print("ERROR: MYSQL_JDBC_URL must include serverTimezone=UTC")
        raise SystemExit(1)
    for name in ("MYSQL_USER", "MYSQL_PASSWORD"):
        if not os.getenv(name):
            print(f"ERROR: {name} is not set")
            raise SystemExit(1)
    print(f"jdbc_host_configured={bool(urlsplit(url[len('jdbc:'):]).hostname)}")
    from pyspark.sql import SparkSession, functions as F

    spark = None
    try:
        spark = (SparkSession.builder.appName("als-readonly-environment-probe")
                 .config("spark.sql.session.timeZone", "UTC").getOrCreate())
        query = """SELECT pr.ratingid, pr.userid, pr.movieid, pr.rating, pr.rated_at
                   FROM personalratings pr
                   JOIN `user` u ON u.userid=pr.userid AND u.deleted_at IS NULL
                   JOIN movieinfo m ON m.movieid=pr.movieid AND m.deleted_at IS NULL
                   WHERE 1=0"""
        frame = (spark.read.format("jdbc").option("url", url)
                 .option("driver", "com.mysql.cj.jdbc.Driver")
                 .option("user", os.environ["MYSQL_USER"])
                 .option("password", os.environ["MYSQL_PASSWORD"])
                 .option("dbtable", f"({query}) AS src").load())
        required = {"ratingid", "userid", "movieid", "rating", "rated_at"}
        missing = required - set(frame.columns)
        if missing:
            raise RuntimeError(f"MySQL schema probe missing columns: {sorted(missing)}")
        print("mysql_readonly_schema_probe=ok")
        sample = (spark.read.format("jdbc").option("url", url)
                  .option("driver", "com.mysql.cj.jdbc.Driver")
                  .option("user", os.environ["MYSQL_USER"])
                  .option("password", os.environ["MYSQL_PASSWORD"])
                  .option("dbtable", "(SELECT pr.ratingid, pr.rated_at, DATE_FORMAT(pr.rated_at,'%Y-%m-%d %H:%i:%s.%f') AS mysql_rated_at_utc, u.userid AS joined_userid, m.movieid AS joined_movieid FROM personalratings pr LEFT JOIN `user` u ON u.userid=pr.userid LEFT JOIN movieinfo m ON m.movieid=pr.movieid WHERE pr.rated_at=(SELECT MAX(rated_at) FROM personalratings) ORDER BY pr.ratingid LIMIT 1) AS src")
                  .load()
                  .select(F.date_format("rated_at", "yyyy-MM-dd HH:mm:ss.SSSSSS")
                          .alias("spark_rated_at_utc"), "ratingid", "mysql_rated_at_utc")
                  .first())
        if sample:
            spark_time = sample.spark_rated_at_utc
            mysql_time = sample.mysql_rated_at_utc
            if spark_time != mysql_time:
                raise RuntimeError(
                    f"JDBC timestamp UTC mismatch for ratingid={sample.ratingid}: "
                    f"mysql_utc={mysql_time}, spark_utc={spark_time}"
                )
            print("mysql_rated_at_utc_roundtrip=ok")
        else:
            print("mysql_rated_at_utc_roundtrip=no_rows")
        freshness_sql = """SELECT
          DATE_FORMAT((SELECT MAX(rated_at) FROM personalratings), '%Y-%m-%d %H:%i:%s.%f') AS latest_rating_at_utc,
          DATE_FORMAT((SELECT MAX(updated_at) FROM `user` WHERE deleted_at IS NULL), '%Y-%m-%d %H:%i:%s.%f') AS latest_user_update_utc,
          DATE_FORMAT((SELECT MAX(updated_at) FROM movieinfo WHERE deleted_at IS NULL), '%Y-%m-%d %H:%i:%s.%f') AS latest_movie_update_utc,
          DATE_FORMAT((SELECT MAX(generated_at) FROM recommendationitem), '%Y-%m-%d %H:%i:%s.%f') AS latest_recommendation_utc
        """
        freshness = (spark.read.format("jdbc").option("url", url)
                     .option("driver", "com.mysql.cj.jdbc.Driver")
                     .option("user", os.environ["MYSQL_USER"])
                     .option("password", os.environ["MYSQL_PASSWORD"])
                     .option("dbtable", f"({freshness_sql}) AS src").load().first().asDict())
        print(f"mysql_freshness_utc={freshness}")
    finally:
        if spark is not None:
            spark.stop()
