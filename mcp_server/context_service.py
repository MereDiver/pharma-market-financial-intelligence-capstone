"""Structured openFDA profile retrieval and FDA-label semantic context."""

from __future__ import annotations

from psycopg2 import sql

try:
    from mcp_server import embeddings, lakebase
    from mcp_server.validation import validate_product, validate_top_n
except ModuleNotFoundError:  # pragma: no cover
    import embeddings, lakebase
    from validation import validate_product, validate_top_n


def _resolve_product(product: str) -> dict | None:
    product = validate_product(product)
    schema = sql.Identifier(lakebase.get_schema_name())
    statement = sql.SQL("""
      SELECT product_key, cms_product_name, brand_name, generic_name, manufacturer_name,
             dosage_form, route, product_type, product_ndc, package_ndc,
             application_number, spl_set_id, substance_name, pharm_class,
             match_method, match_status
      FROM {}.drug_products
      WHERE product_key=%s OR lower(brand_name)=lower(%s) OR lower(generic_name)=lower(%s)
         OR lower(cms_product_name)=lower(%s)
      ORDER BY CASE WHEN product_key=%s THEN 0 ELSE 1 END LIMIT 2
    """).format(schema)
    rows = lakebase.run_query(statement, (product, product, product, product, product))
    return rows[0] if len(rows) == 1 else ({"ambiguous": True, "candidates": rows} if rows else None)


def get_drug_profile(product: str) -> dict:
    resolved = _resolve_product(product)
    if not resolved:
        return {"status": "not_found", "message": "No confirmed openFDA profile is stored for this product."}
    if resolved.get("ambiguous"):
        return {"status": "ambiguous", "candidates": resolved["candidates"]}
    return {"status": "success", "profile": resolved,
            "limitation": "FDA metadata is product context, not medical advice."}


def search_drug_context(query: str, product: str | None = None, top_k: int = 5) -> dict:
    query = validate_product(query)
    top_k = validate_top_n(top_k, 10)
    key = None
    if product:
        resolved = _resolve_product(product)
        if not resolved:
            return {"status": "not_found", "message": "Product is not enriched."}
        if resolved.get("ambiguous"):
            return {"status": "ambiguous", "candidates": resolved["candidates"]}
        key = resolved["product_key"]
    return {"status": "success", "results": embeddings.semantic_search(query, top_k, key),
            "limitation": "Retrieved text is FDA-label context and is not medical advice."}
