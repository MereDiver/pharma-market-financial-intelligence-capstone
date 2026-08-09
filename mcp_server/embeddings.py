"""Lazy MiniLM embeddings, content-aware ingestion, and pgvector search."""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Any, Iterable, Sequence

from psycopg2 import sql
from psycopg2.extras import execute_values

try:
    from mcp_server import lakebase
except ModuleNotFoundError:  # pragma: no cover
    import lakebase

MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_DIM = 384
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
_model: Any | None = None
_model_lock = threading.Lock()


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller")
    if not isinstance(text, str) or not text.strip():
        return []
    chunks, step = [], chunk_size - overlap
    for start in range(0, len(text), step):
        chunk = text[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks


def get_embedding_model() -> Any:
    global _model
    if MODEL_NAME != "sentence-transformers/all-MiniLM-L6-v2":
        raise ValueError("The supported embedding model is sentence-transformers/all-MiniLM-L6-v2.")
    if _model is None:
        with _model_lock:
            if _model is None:
                os.environ.setdefault("HF_HOME", "/tmp/pharma-huggingface-cache")
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(MODEL_NAME, cache_folder=os.environ["HF_HOME"])
    return _model


def embed_texts(texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
    if not texts:
        return []
    vectors = get_embedding_model().encode(list(texts), batch_size=batch_size,
                                           show_progress_bar=False, normalize_embeddings=True)
    output = [[float(value) for value in vector] for vector in vectors]
    if any(len(vector) != EMBEDDING_DIM for vector in output):
        raise RuntimeError("Unexpected embedding dimension.")
    return output


def vector_literal(vector: Iterable[float]) -> str:
    values = list(float(value) for value in vector)
    if len(values) != EMBEDDING_DIM:
        raise ValueError("Expected a 384-dimensional embedding.")
    return "[" + ",".join(format(value, ".9g") for value in values) + "]"


def ingest_changed_documents(limit: int | None = None) -> dict[str, int]:
    lakebase.ensure_schema()
    schema = sql.Identifier(lakebase.get_schema_name())
    limit_clause = sql.SQL(" LIMIT %s") if limit is not None else sql.SQL("")
    params = (MODEL_NAME, limit) if limit is not None else (MODEL_NAME,)
    statement = sql.SQL("""
        SELECT d.document_id, d.product_key, d.narrative_text, d.content_hash
        FROM {}.drug_documents d
        WHERE NOT EXISTS (
          SELECT 1 FROM {}.drug_embeddings e
          WHERE e.document_id=d.document_id AND e.model_name=%s
            AND e.document_content_hash=d.content_hash)
        ORDER BY d.synced_at, d.document_id
    """).format(schema, schema) + limit_clause
    documents = lakebase.run_query(statement, params)
    summary = {"documents_selected": len(documents), "documents_embedded": 0, "chunks_written": 0}
    for document in documents:
        chunks = chunk_text(document["narrative_text"])
        vectors = embed_texts(chunks)
        rows = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            key = f"{document['document_id']}|{index}|{MODEL_NAME}|{document['content_hash']}"
            rows.append((hashlib.sha256(key.encode()).hexdigest(), document["document_id"],
                         document["product_key"], index, chunk, vector_literal(vector),
                         MODEL_NAME, document["content_hash"]))
        delete = sql.SQL("DELETE FROM {}.drug_embeddings WHERE document_id=%s AND model_name=%s").format(schema)
        insert = sql.SQL("""
          INSERT INTO {}.drug_embeddings
          (embedding_id,document_id,product_key,chunk_index,chunk_text,embedding,model_name,document_content_hash)
          VALUES %s
        """).format(schema)
        with lakebase.get_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(delete, (document["document_id"], MODEL_NAME))
                    if rows:
                        execute_values(cursor, insert.as_string(cursor), rows,
                                       template="(%s,%s,%s,%s,%s,%s::vector,%s,%s)", page_size=200)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        summary["documents_embedded"] += 1
        summary["chunks_written"] += len(rows)
    return summary


def semantic_search(query: str, top_k: int = 5, product_key: str | None = None) -> list[dict[str, Any]]:
    vector = vector_literal(embed_texts([query])[0])
    schema = sql.Identifier(lakebase.get_schema_name())
    product_filter = sql.SQL(" AND e.product_key=%s") if product_key else sql.SQL("")
    params: list[Any] = [vector, MODEL_NAME]
    if product_key:
        params.append(product_key)
    params.extend([vector, top_k])
    statement = sql.SQL("""
      SELECT e.product_key, COALESCE(p.brand_name,p.generic_name,p.cms_product_name) AS product,
             d.section_names, e.chunk_index, e.chunk_text,
             1-(e.embedding <=> %s::vector) AS similarity,
             d.source, d.source_identifier
      FROM {}.drug_embeddings e
      JOIN {}.drug_documents d ON d.document_id=e.document_id
      JOIN {}.drug_products p ON p.product_key=e.product_key
      WHERE e.model_name=%s
    """).format(schema, schema, schema) + product_filter + sql.SQL(" ORDER BY e.embedding <=> %s::vector LIMIT %s")
    return lakebase.run_query(statement, tuple(params))
