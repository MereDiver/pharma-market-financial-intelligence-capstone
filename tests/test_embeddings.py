from mcp_server import embeddings


def test_chunking_and_semantic_search_are_mockable(monkeypatch):
    assert embeddings.chunk_text("abcdefghij", 6, 2) == ["abcdef", "efghij"]
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[0.0] * 384])
    expected=[{"product":"Example","chunk_text":"FDA context","similarity":.9}]
    monkeypatch.setattr(embeddings.lakebase, "run_query", lambda statement, params: expected)
    assert embeddings.semantic_search("purpose", 1) == expected

