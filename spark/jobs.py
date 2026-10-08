"""PySpark re-implementations of the three heaviest Stage-4 analyses.

Each function mirrors one analysis SQL file exactly (same filters, window frames, rounding), so the
result can be reconciled row by row with the DuckDB output:

  issuer_ranking     <-> analysis/04_issuer_performance_ranking.sql  (part A)
  chargeback_anomaly <-> analysis/05_chargeback_anomaly_detection.sql (part A)
  card_testing       <-> analysis/06_cnp_risk_analysis.sql           (part A)

Spark-specific choices are commented inline: broadcast joins for small dimensions, column pruning,
partition pruning on the month-partitioned fact, and an exact `percentile` for the rolling median.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F


def build_spark(app_name: str = "card-network-analytics", shuffle_partitions: int = 16,
                driver_memory: str = "4g") -> SparkSession:
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.driver.memory", driver_memory)
        # Default 200 shuffle partitions is tuned for clusters; on a laptop most would be tiny tasks.
        .config("spark.sql.shuffle.partitions", shuffle_partitions)
        # Adaptive Query Execution: coalesces small shuffle partitions, handles skew, switches join strategy.
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )


def _flag(cond) -> F.Column:
    return F.when(cond, 1).otherwise(0)


# ---------------------------------------------------------------------------------------------
# 04A - Issuer performance ranking
# ---------------------------------------------------------------------------------------------
def issuer_ranking(fct: DataFrame, dim_issuer: DataFrame) -> DataFrame:
    cnp = F.col("channel") == "card_not_present"
    agg = (
        fct.select("issuer_id", "is_approved", "channel", "auth_response_code",  # column pruning
                   "fraud_loss_amount_usd", "approved_amount_usd")
        .groupBy("issuer_id")
        .agg(
            F.count("*").alias("attempts"),
            F.sum(_flag(F.col("is_approved"))).alias("approved"),
            F.sum(_flag(cnp & F.col("is_approved"))).alias("cnp_approved"),
            F.sum(_flag(cnp)).alias("cnp_attempts"),
            F.sum(_flag(F.col("auth_response_code") == "05")).alias("dnh"),
            F.sum(_flag(F.col("auth_response_code") == "91")).alias("issuer_unavailable_declines"),
            F.sum("fraud_loss_amount_usd").cast("double").alias("fraud_usd"),
            F.sum("approved_amount_usd").cast("double").alias("approved_usd"),
        )
        .where(F.col("attempts") >= 5000)
        .withColumn("approval_rate", F.col("approved") / F.col("attempts"))
        .withColumn("cnp_approval_rate", F.col("cnp_approved") / F.when(F.col("cnp_attempts") != 0, F.col("cnp_attempts")))
        .withColumn("do_not_honor_rate", F.col("dnh") / F.col("attempts"))
        .withColumn("fraud_loss_bps", F.col("fraud_usd") * 10000 / F.when(F.col("approved_usd") != 0, F.col("approved_usd")))
    )
    # dim_issuer has 45 rows: broadcast it instead of shuffling the aggregate.
    joined = agg.join(F.broadcast(dim_issuer.select("issuer_id", "issuer_name", "issuer_country", "issuer_type")),
                      "issuer_id")
    # Global windows (no PARTITION BY) run in a single task: fine on ~45 rows, a red flag on big data.
    w_all = Window.partitionBy()
    return joined.select(
        "issuer_id", "issuer_name", "issuer_country", "issuer_type", "attempts",
        F.round("approval_rate", 4).alias("approval_rate"),
        F.round("cnp_approval_rate", 4).alias("cnp_approval_rate"),
        F.round("do_not_honor_rate", 4).alias("do_not_honor_rate"),
        "issuer_unavailable_declines",
        F.round("fraud_loss_bps", 1).alias("fraud_loss_bps"),
        F.dense_rank().over(Window.orderBy(F.desc("approval_rate"))).alias("approval_rank"),
        F.round(F.percent_rank().over(Window.orderBy("cnp_approval_rate")), 3).alias("cnp_approval_percentile"),
        F.round((F.col("cnp_approval_rate") - F.avg("cnp_approval_rate").over(w_all))
                / F.stddev_samp("cnp_approval_rate").over(w_all), 2).alias("cnp_approval_zscore"),
        F.ntile(4).over(Window.orderBy("fraud_loss_bps", "issuer_id")).alias("fraud_loss_quartile"),
    )


# ---------------------------------------------------------------------------------------------
# 05A - Chargeback anomaly detection
# ---------------------------------------------------------------------------------------------
def chargeback_anomaly(fct: DataFrame, dim_merchant: DataFrame) -> DataFrame:
    merchant = (
        fct.select("merchant_id", "is_approved", "is_chargeback", "is_fraud", "chargeback_amount_usd")
        .groupBy("merchant_id")  # shuffle #1: hash-partition ~20k merchant keys
        .agg(
            F.sum(_flag(F.col("is_approved"))).alias("approved"),
            F.sum(_flag(F.col("is_chargeback"))).alias("chargebacks"),
            F.sum(_flag(F.col("is_chargeback") & ~F.col("is_fraud"))).alias("non_fraud_chargebacks"),
            F.sum("chargeback_amount_usd").cast("double").alias("chargeback_usd"),
        )
        .where(F.col("approved") >= 100)
        .join(F.broadcast(dim_merchant.select("merchant_id", "merchant_name", "mcc", "mcc_category", "acquirer_name")),
              "merchant_id")
        .withColumn("cb_rate", F.col("chargebacks") / F.col("approved"))
    )
    w_peer = Window.partitionBy("mcc")  # shuffle #2: co-locate each MCC's merchants for peer statistics
    scored = (merchant
              .withColumn("peer_avg", F.avg("cb_rate").over(w_peer))
              .withColumn("peer_sd", F.stddev_samp("cb_rate").over(w_peer))
              .withColumn("z", (F.col("cb_rate") - F.col("peer_avg")) / F.when(F.col("peer_sd") != 0, F.col("peer_sd"))))
    flagged = scored.where((F.col("cb_rate") >= 0.01) & (F.col("chargebacks") >= 5))
    return flagged.select(
        "merchant_id", "merchant_name", "mcc", "mcc_category", "acquirer_name", "approved", "chargebacks",
        "non_fraud_chargebacks",
        F.round("chargeback_usd", 2).alias("chargeback_usd"),
        F.round("cb_rate", 4).alias("chargeback_rate"),
        F.round("peer_avg", 4).alias("peer_avg_chargeback_rate"),
        F.round("z", 1).alias("peer_zscore"),
        F.when(F.col("z") >= 3, "HIGH: above 1% / 5 disputes and 3+ sd above MCC peers")
         .otherwise("MEDIUM: above 1% / 5 disputes").alias("alert_level"),
        F.row_number().over(Window.orderBy(F.desc("cb_rate"), "merchant_id")).alias("risk_rank"),
    )


# ---------------------------------------------------------------------------------------------
# 06A - Card-testing detection (rolling 28-day median baseline per acquirer)
# ---------------------------------------------------------------------------------------------
def card_testing(fct: DataFrame, dim_acquirer: DataFrame) -> DataFrame:
    daily = (
        fct.where(F.col("channel") == "card_not_present")  # predicate pushdown into the Parquet scan
        .select("acquirer_id", "transaction_date", "amount_usd", "auth_response_code", "is_fraud")
        .groupBy("acquirer_id", "transaction_date")
        .agg(
            F.count("*").alias("cnp_attempts"),
            F.sum(_flag(F.col("amount_usd") < 5)).alias("small_ticket_attempts"),
            F.sum(_flag(F.col("auth_response_code").isin("14", "54"))).alias("invalid_or_expired_declines"),
            F.sum(_flag(F.col("is_fraud"))).alias("fraud_attempts"),
        )
        .join(F.broadcast(dim_acquirer.select("acquirer_id", "acquirer_name", "acquirer_type")), "acquirer_id")
    )
    # ROWS frame identical to the SQL: 28 preceding .. 1 preceding (excludes the current day).
    w = Window.partitionBy("acquirer_id").orderBy("transaction_date").rowsBetween(-28, -1)
    base = (daily
            # exact median (percentile_approx would not reconcile with DuckDB's exact median)
            .withColumn("baseline_median", F.expr("percentile(invalid_or_expired_declines, 0.5)").over(w))
            .withColumn("baseline_small_ticket_share",
                        F.avg(F.col("small_ticket_attempts") / F.col("cnp_attempts")).over(w)))
    floor1 = F.greatest(F.col("baseline_median"), F.lit(1.0))
    return (base
            .where(F.col("baseline_median").isNotNull()
                   & (F.col("invalid_or_expired_declines") >= 5 * floor1)
                   & (F.col("invalid_or_expired_declines") >= 20))
            .select("acquirer_id", "acquirer_name", "acquirer_type", "transaction_date", "cnp_attempts",
                    "small_ticket_attempts", "invalid_or_expired_declines",
                    F.col("baseline_median").alias("baseline_28d_median"),
                    F.round(F.col("invalid_or_expired_declines") / floor1, 1).alias("multiple_of_baseline"),
                    F.round(F.col("small_ticket_attempts") / F.col("cnp_attempts"), 3).alias("small_ticket_share"),
                    F.round("baseline_small_ticket_share", 3).alias("baseline_small_ticket_share"),
                    "fraud_attempts"))


JOBS = {
    # name: (spark function, dimension parquet, analysis file, statement index, key columns)
    "issuer_ranking": (issuer_ranking, "dim_issuer", "04_issuer_performance_ranking.sql", 0, ["issuer_id"]),
    "chargeback_anomaly": (chargeback_anomaly, "dim_merchant", "05_chargeback_anomaly_detection.sql", 0, ["merchant_id"]),
    "card_testing": (card_testing, "dim_acquirer", "06_cnp_risk_analysis.sql", 0, ["acquirer_id", "transaction_date"]),
}
