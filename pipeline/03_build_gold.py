"""Build compact quarterly, YoY, state, and portfolio Gold analytical tables."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pyspark.sql import SparkSession, functions as F

from config.job_args import configure_from_args
from config.project_config import load_config


def _safe_ratio(numerator: str, denominator: str):
    return F.when(F.col(denominator).isNotNull() & (F.col(denominator) != 0), F.col(numerator) / F.col(denominator))


def _write(frame, table: str) -> None:
    frame.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)


def main() -> None:
    configure_from_args()
    spark = SparkSession.builder.getOrCreate()
    cfg = load_config()
    clean = spark.table(f"{cfg.table_prefix}.silver_medicaid_utilization_clean").filter(
        (~F.col("suppression_used")) & F.col("total_reimbursement").isNotNull()
    )
    grain = ["year", "quarter", "state", "utilization_type", "product_key"]
    quarterly = clean.groupBy(*grain).agg(
        F.first("cms_product_name", ignorenulls=True).alias("display_product_name"),
        F.sum("prescriptions").alias("prescriptions"),
        F.sum("units_reimbursed").alias("units_reimbursed"),
        F.sum("total_reimbursement").alias("total_reimbursement"),
        F.sum("medicaid_reimbursement").alias("medicaid_reimbursement"),
        F.sum("non_medicaid_reimbursement").alias("non_medicaid_reimbursement"),
        F.countDistinct("ndc_11").alias("package_ndc_count"),
    ).withColumn("reimbursement_per_prescription", _safe_ratio("total_reimbursement", "prescriptions")) \
     .withColumn("reimbursement_per_unit", _safe_ratio("total_reimbursement", "units_reimbursed"))
    _write(quarterly, f"{cfg.table_prefix}.gold_drug_performance_quarterly")

    keys = ["quarter", "state", "utilization_type", "product_key"]
    current = quarterly.alias("c")
    prior = quarterly.alias("p")
    joined = current.join(
        prior,
        (F.col("c.product_key") == F.col("p.product_key")) &
        (F.col("c.state") == F.col("p.state")) &
        (F.col("c.utilization_type") == F.col("p.utilization_type")) &
        (F.col("c.quarter") == F.col("p.quarter")) &
        (F.col("c.year") == F.col("p.year") + 1),
        "inner",
    )
    def pct(current_col, prior_col):
        return F.when(F.col(prior_col) != 0, (F.col(current_col) - F.col(prior_col)) / F.col(prior_col))
    yoy = joined.select(
        F.col("c.year").alias("current_year"), F.col("p.year").alias("prior_year"),
        *[F.col(f"c.{key}").alias(key) for key in keys], F.col("c.display_product_name"),
        F.col("c.prescriptions").alias("current_prescriptions"), F.col("p.prescriptions").alias("prior_prescriptions"),
        F.col("c.units_reimbursed").alias("current_units_reimbursed"), F.col("p.units_reimbursed").alias("prior_units_reimbursed"),
        F.col("c.total_reimbursement").alias("current_total_reimbursement"), F.col("p.total_reimbursement").alias("prior_total_reimbursement"),
        F.col("c.reimbursement_per_prescription").alias("current_reimbursement_per_prescription"),
        F.col("p.reimbursement_per_prescription").alias("prior_reimbursement_per_prescription"),
    ).withColumn("reimbursement_change", F.col("current_total_reimbursement") - F.col("prior_total_reimbursement")) \
     .withColumn("reimbursement_change_percent", pct("current_total_reimbursement", "prior_total_reimbursement")) \
     .withColumn("prescription_change", F.col("current_prescriptions") - F.col("prior_prescriptions")) \
     .withColumn("prescription_change_percent", pct("current_prescriptions", "prior_prescriptions")) \
     .withColumn("rate_change", F.col("current_reimbursement_per_prescription") - F.col("prior_reimbursement_per_prescription")) \
     .withColumn("rate_change_percent", pct("current_reimbursement_per_prescription", "prior_reimbursement_per_prescription")) \
     .withColumn("volume_effect", (F.col("current_prescriptions") - F.col("prior_prescriptions")) * ((F.col("prior_reimbursement_per_prescription") + F.col("current_reimbursement_per_prescription")) / 2)) \
     .withColumn("reimbursement_per_prescription_effect", (F.col("current_reimbursement_per_prescription") - F.col("prior_reimbursement_per_prescription")) * ((F.col("prior_prescriptions") + F.col("current_prescriptions")) / 2)) \
     .withColumn("reconciliation_difference", F.col("reimbursement_change") - F.col("volume_effect") - F.col("reimbursement_per_prescription_effect"))
    _write(yoy, f"{cfg.table_prefix}.gold_drug_performance_yoy")

    state = clean.groupBy("year", "quarter", "state", "utilization_type").agg(
        F.sum("prescriptions").alias("prescriptions"), F.sum("units_reimbursed").alias("units_reimbursed"),
        F.sum("total_reimbursement").alias("total_reimbursement"), F.sum("medicaid_reimbursement").alias("medicaid_reimbursement"),
        F.countDistinct("product_key").alias("product_count"),
    ).withColumn("reimbursement_per_prescription", _safe_ratio("total_reimbursement", "prescriptions"))
    _write(state, f"{cfg.table_prefix}.gold_state_performance")
    portfolio = clean.groupBy("year", "quarter").agg(
        F.sum("prescriptions").alias("prescriptions"), F.sum("units_reimbursed").alias("units_reimbursed"),
        F.sum("total_reimbursement").alias("total_reimbursement"), F.sum("medicaid_reimbursement").alias("medicaid_reimbursement"),
        F.sum("non_medicaid_reimbursement").alias("non_medicaid_reimbursement"),
        F.countDistinct("product_key").alias("product_count"), F.countDistinct("state").alias("state_count"),
    ).withColumn("reimbursement_per_prescription", _safe_ratio("total_reimbursement", "prescriptions"))
    _write(portfolio, f"{cfg.table_prefix}.gold_portfolio_summary")
    print("Gold build complete: quarterly, YoY, state, and portfolio tables.")


if __name__ == "__main__":
    main()
