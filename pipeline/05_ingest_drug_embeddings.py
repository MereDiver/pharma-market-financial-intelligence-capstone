"""Embed only new/content-changed openFDA label documents into Lakebase pgvector."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.job_args import configure_from_args
from mcp_server.embeddings import ingest_changed_documents


if __name__ == "__main__":
    configure_from_args()
    summary = ingest_changed_documents()
    print(f"Embedding ingestion complete: {summary}")
