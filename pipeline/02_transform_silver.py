"""Normalize Bronze strings into a typed, suppression-aware Silver Delta table."""

from __future__ import annotations

import sys
from pathlib import Path

# Databricks serverless uses ``filename`` when ``__file__`` is unavailable.
SOURCE_PATH = globals().get("__file__") or globals().get("filename")
if not SOURCE_PATH:
    raise RuntimeError("Unable to determine the pipeline source path.")
ROOT = Path(str(SOURCE_PATH)).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pyspark.sql import SparkSession, functions as F

from config.job_args import configure_from_args
from config.project_config import load_config


def main() -> None:
    configure_from_args()
    spark = SparkSession.builder.getOrCreate()
    cfg = load_config()
    bronze = spark.table(f"{cfg.table_prefix}.bronze_raw_medicaid_utilization")
    ndc = F.lpad(F.regexp_replace(F.col("ndc"), r"\D", ""), 11, "0")
    suppression = F.lower(F.trim(F.col("suppression_used"))).isin("true", "1", "yes", "y")
    silver = bronze.select(
        F.upper(F.trim("utilization_type")).alias("utilization_type"),
        F.upper(F.trim("state")).alias("state"),
        ndc.alias("ndc_11"),
        F.lpad(F.trim("labeler_code"), 5, "0").alias("labeler_code"),
        F.lpad(F.trim("product_code"), 4, "0").alias("product_code"),
        F.lpad(F.trim("package_size"), 2, "0").alias("package_code"),
        F.col("year").cast("int").alias("year"),
        F.col("quarter").cast("int").alias("quarter"),
        F.concat(F.col("year"), F.lit("-Q"), F.col("quarter")).alias("period"),
        suppression.alias("suppression_used"),
        F.trim("product_name").alias("cms_product_name"),
        F.when(~suppression, F.col("units_reimbursed").cast("decimal(24,3)")).alias("units_reimbursed"),
        F.when(~suppression, F.col("number_of_prescriptions").cast("long")).alias("prescriptions"),
        F.when(~suppression, F.col("total_amount_reimbursed").cast("decimal(24,2)")).alias("total_reimbursement"),
        F.when(~suppression, F.col("medicaid_amount_reimbursed").cast("decimal(24,2)")).alias("medicaid_reimbursement"),
        F.when(~suppression, F.col("non_medicaid_amount_reimbursed").cast("decimal(24,2)")).alias("non_medicaid_reimbursement"),
        F.concat(F.lpad(F.trim("labeler_code"), 5, "0"), F.lpad(F.trim("product_code"), 4, "0")).alias("product_key"),
        "record_hash", "source_year", "source_identifier", "source_mode", "source_url", "ingested_at",
    ).filter(
        F.col("year").isin(list(cfg.years)) & F.col("state").isin(list(cfg.states)) &
        F.col("quarter").between(1, 4) & (F.length("ndc_11") == 11)
    ).dropDuplicates(["record_hash"])
    target = f"{cfg.table_prefix}.silver_medicaid_utilization_clean"
    silver.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(target)
    print(f"Silver transformation complete: {target}; rows={silver.count()}")


if __name__ == "__main__":
    main()
