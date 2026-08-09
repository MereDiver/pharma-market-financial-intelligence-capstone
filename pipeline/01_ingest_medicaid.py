"""Ingest a bounded real CMS subset into an idempotent Bronze Delta table."""

from __future__ import annotations

import sys
from pathlib import Path

# Databricks serverless executes Python files through ``exec`` and does not
# always populate ``__file__``. Its wrapper does expose the source as
# ``filename``, while normal Python execution continues to use ``__file__``.
SOURCE_PATH = globals().get("__file__") or globals().get("filename")
if not SOURCE_PATH:
    raise RuntimeError("Unable to determine the pipeline source path.")
ROOT = Path(str(SOURCE_PATH)).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pyspark.sql import SparkSession, functions as F, types as T

from config.job_args import configure_from_args
from config.project_config import CMS_DATASETS, load_config
from pipeline.cms_medicaid_client import CMSMedicaidClient

RAW_FIELDS = (
    "utilization_type", "state", "ndc", "labeler_code", "product_code", "package_size",
    "year", "quarter", "suppression_used", "product_name", "units_reimbursed",
    "number_of_prescriptions", "total_amount_reimbursed", "medicaid_amount_reimbursed",
    "non_medicaid_amount_reimbursed",
)
RAW_SCHEMA = T.StructType([T.StructField(name, T.StringType(), True) for name in RAW_FIELDS])


def _canonical_rows(records: list[dict], source_year: int, source_mode: str,
                    source_identifier: str, source_url: str) -> list[dict]:
    output = []
    for record in records:
        row = {field: None if record.get(field) is None else str(record.get(field)) for field in RAW_FIELDS}
        row.update(source_year=source_year, source_mode=source_mode,
                   source_identifier=source_identifier, source_url=source_url)
        output.append(row)
    return output


def main() -> None:
    configure_from_args()
    spark = SparkSession.builder.getOrCreate()
    cfg = load_config()
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{cfg.catalog}`.`{cfg.schema}`")
    stage = f"{cfg.table_prefix}._bronze_medicaid_stage"
    bronze = f"{cfg.table_prefix}.bronze_raw_medicaid_utilization"
    schema = RAW_SCHEMA.add("source_year", T.IntegerType(), False).add("source_mode", T.StringType(), False).add("source_identifier", T.StringType(), False).add("source_url", T.StringType(), False)
    client = CMSMedicaidClient(page_size=cfg.cms_page_size)
    wrote = False
    buffered_rows: list[dict] = []

    def flush() -> None:
        nonlocal wrote, buffered_rows
        if not buffered_rows:
            return
        rows_to_write, buffered_rows = buffered_rows, []
        frame = spark.createDataFrame(rows_to_write, schema=schema)
        mode = "append" if wrote else "overwrite"
        frame.write.format("delta").mode(mode).option("overwriteSchema", "true").saveAsTable(stage)
        wrote = True

    def persist(records: list[dict], year: int, identifier: str, url: str) -> None:
        nonlocal buffered_rows
        rows = _canonical_rows(records, year, cfg.cms_mode, identifier, url)
        buffered_rows.extend(rows)
        if len(buffered_rows) >= cfg.cms_write_batch_size:
            flush()

    for year in cfg.years:
        source = CMS_DATASETS[year]
        if cfg.cms_mode == "api":
            api_url = f"https://data.medicaid.gov/api/1/datastore/query/{source['dataset_id']}/0"
            for state in cfg.states:
                for page in client.iter_api_pages(source["dataset_id"], state):
                    persist(page, year, source["dataset_id"], api_url)
        else:
            for page in client.iter_bulk_batches(source["bulk_url"], set(cfg.states)):
                persist(page, year, source["dataset_id"], source["bulk_url"])

    flush()
    if not wrote:
        raise RuntimeError("CMS returned no records for the configured scope.")
    staged = spark.table(stage).withColumn(
        "record_hash",
        F.sha2(F.concat_ws("||", *[F.coalesce(F.col(name), F.lit("<NULL>")) for name in RAW_FIELDS], F.col("source_identifier")), 256),
    ).withColumn("ingested_at", F.current_timestamp()).dropDuplicates(["record_hash"])
    staged.createOrReplaceTempView("bronze_medicaid_deduplicated")
    if not spark.catalog.tableExists(bronze):
        staged.write.format("delta").mode("overwrite").saveAsTable(bronze)
    else:
        spark.sql(f"""
            MERGE INTO {bronze} target
            USING bronze_medicaid_deduplicated source
            ON target.record_hash = source.record_hash
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
        """)
    spark.sql(f"DROP TABLE IF EXISTS {stage}")
    print(f"Bronze ingestion complete: {bronze}; rows={spark.table(bronze).count()}")


if __name__ == "__main__":
    main()
