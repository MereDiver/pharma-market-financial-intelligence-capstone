"""Embed only new/content-changed openFDA label documents into Lakebase pgvector."""

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

from config.job_args import configure_from_args
from mcp_server.embeddings import ingest_changed_documents


if __name__ == "__main__":
    configure_from_args()
    summary = ingest_changed_documents()
    print(f"Embedding ingestion complete: {summary}")
