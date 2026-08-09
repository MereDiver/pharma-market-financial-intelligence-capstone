"""Enrich only top reimbursed products with openFDA metadata and label text."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

# Databricks serverless uses ``filename`` when ``__file__`` is unavailable.
SOURCE_PATH = globals().get("__file__") or globals().get("filename")
if not SOURCE_PATH:
    raise RuntimeError("Unable to determine the pipeline source path.")
ROOT = Path(str(SOURCE_PATH)).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from psycopg2 import sql
from pyspark.sql import SparkSession, functions as F, types as T

from config.job_args import configure_from_args
from config.project_config import load_config
from mcp_server import lakebase
from pipeline.openfda_client import OpenFDAClient


def _document(product_key: str, metadata: dict, label: dict) -> dict:
    sections = label["sections"]
    narrative = "\n\n".join(f"{name.replace('_', ' ').title()}\n{text}" for name, text in sections.items())
    content_hash = hashlib.sha256(narrative.encode("utf-8")).hexdigest()
    source_identifier = str(label.get("source_identifier") or metadata.get("spl_set_id") or product_key)
    return {
        "document_id": hashlib.sha256(f"openfda-label|{source_identifier}".encode()).hexdigest(),
        "product_key": product_key, "brand_name": metadata.get("brand_name"),
        "generic_name": metadata.get("generic_name"), "manufacturer_name": metadata.get("manufacturer_name"),
        "section_names": list(sections), "narrative_text": narrative, "source": "openFDA Drug Label",
        "source_identifier": source_identifier, "payload": label["payload"], "content_hash": content_hash,
    }


def _upsert(product_key: str, ndc_11: str, cms_name: str, metadata: dict,
            document: dict | None) -> None:
    schema = sql.Identifier(lakebase.get_schema_name())
    with lakebase.get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("""
                  INSERT INTO {}.drug_products
                  (product_key,ndc_11,cms_product_name,brand_name,generic_name,manufacturer_name,
                   dosage_form,route,product_type,product_ndc,package_ndc,application_number,spl_set_id,
                   substance_name,pharm_class,match_method,match_status,payload,synced_at)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,now())
                  ON CONFLICT(product_key) DO UPDATE SET
                    ndc_11=EXCLUDED.ndc_11,cms_product_name=EXCLUDED.cms_product_name,
                    brand_name=EXCLUDED.brand_name,generic_name=EXCLUDED.generic_name,
                    manufacturer_name=EXCLUDED.manufacturer_name,dosage_form=EXCLUDED.dosage_form,
                    route=EXCLUDED.route,product_type=EXCLUDED.product_type,product_ndc=EXCLUDED.product_ndc,
                    package_ndc=EXCLUDED.package_ndc,application_number=EXCLUDED.application_number,
                    spl_set_id=EXCLUDED.spl_set_id,substance_name=EXCLUDED.substance_name,
                    pharm_class=EXCLUDED.pharm_class,match_method=EXCLUDED.match_method,
                    match_status=EXCLUDED.match_status,payload=EXCLUDED.payload,synced_at=now()
                """).format(schema), (
                    product_key, ndc_11, cms_name, metadata.get("brand_name"), metadata.get("generic_name"),
                    metadata.get("manufacturer_name"), metadata.get("dosage_form"), metadata.get("route"),
                    metadata.get("product_type"), metadata.get("product_ndc"), json.dumps(metadata.get("package_ndc") or []),
                    metadata.get("application_number"), metadata.get("spl_set_id"), metadata.get("substance_name"),
                    json.dumps(metadata.get("pharm_class")), metadata.get("match_method", "none"),
                    metadata.get("match_status", "unmatched"), json.dumps(metadata.get("payload") or {}),
                ))
                if document:
                    cursor.execute(sql.SQL("""
                      INSERT INTO {}.drug_documents
                      (document_id,product_key,brand_name,generic_name,manufacturer_name,section_names,
                       narrative_text,source,source_identifier,payload,content_hash,synced_at)
                      VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,now())
                      ON CONFLICT(document_id) DO UPDATE SET product_key=EXCLUDED.product_key,
                       brand_name=EXCLUDED.brand_name,generic_name=EXCLUDED.generic_name,
                       manufacturer_name=EXCLUDED.manufacturer_name,section_names=EXCLUDED.section_names,
                       narrative_text=EXCLUDED.narrative_text,payload=EXCLUDED.payload,
                       content_hash=EXCLUDED.content_hash,synced_at=now()
                    """).format(schema), (
                        document["document_id"], product_key, document["brand_name"], document["generic_name"],
                        document["manufacturer_name"], json.dumps(document["section_names"]), document["narrative_text"],
                        document["source"], document["source_identifier"], json.dumps(document["payload"]), document["content_hash"],
                    ))
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def main() -> None:
    configure_from_args()
    cfg = load_config()
    spark = SparkSession.builder.getOrCreate()
    lakebase.ensure_schema()
    gold = spark.table(f"{cfg.table_prefix}.gold_drug_performance_quarterly")
    silver = spark.table(f"{cfg.table_prefix}.silver_medicaid_utilization_clean")
    top = gold.groupBy("product_key").agg(
        F.sum("total_reimbursement").alias("total_reimbursement"),
        F.first("display_product_name", ignorenulls=True).alias("cms_product_name"),
    ).orderBy(F.desc("total_reimbursement")).limit(cfg.max_openfda_products)
    representatives = silver.groupBy("product_key").agg(F.first("ndc_11", ignorenulls=True).alias("ndc_11"))
    selected = top.join(representatives, "product_key").collect()  # Explicitly bounded to <= MAX_OPENFDA_PRODUCTS.
    client = OpenFDAClient(api_key=os.getenv("OPENFDA_API_KEY") or None)
    results = []
    for row in selected:
        metadata = client.match_ndc(row.ndc_11, row.cms_product_name)
        label = client.get_label(metadata) if metadata.get("match_status") in {"matched", "fallback"} else None
        document = _document(row.product_key, metadata, label) if label and label.get("sections") else None
        _upsert(row.product_key, row.ndc_11, row.cms_product_name, metadata, document)
        results.append({
            "product_key": row.product_key, "ndc_11": row.ndc_11, "cms_product_name": row.cms_product_name,
            "brand_name": metadata.get("brand_name"), "generic_name": metadata.get("generic_name"),
            "manufacturer_name": metadata.get("manufacturer_name"), "match_method": metadata.get("match_method"),
            "match_status": metadata.get("match_status"), "has_label_document": document is not None,
        })
    output_schema = T.StructType([
        T.StructField("product_key", T.StringType(), False), T.StructField("ndc_11", T.StringType(), False),
        T.StructField("cms_product_name", T.StringType(), True), T.StructField("brand_name", T.StringType(), True),
        T.StructField("generic_name", T.StringType(), True), T.StructField("manufacturer_name", T.StringType(), True),
        T.StructField("match_method", T.StringType(), True), T.StructField("match_status", T.StringType(), True),
        T.StructField("has_label_document", T.BooleanType(), False),
    ])
    spark.createDataFrame(results, output_schema).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{cfg.table_prefix}.openfda_product_enrichment")
    print(f"openFDA enrichment complete: products={len(results)}, labels={sum(bool(r['has_label_document']) for r in results)}")


if __name__ == "__main__":
    main()
