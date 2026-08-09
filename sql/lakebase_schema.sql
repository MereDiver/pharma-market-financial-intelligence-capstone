CREATE SCHEMA IF NOT EXISTS pharma_intelligence;

CREATE TABLE IF NOT EXISTS pharma_intelligence.drug_products (
    product_key TEXT PRIMARY KEY,
    ndc_11 TEXT NOT NULL,
    cms_product_name TEXT,
    brand_name TEXT,
    generic_name TEXT,
    manufacturer_name TEXT,
    dosage_form TEXT,
    route TEXT,
    product_type TEXT,
    product_ndc TEXT,
    package_ndc JSONB NOT NULL DEFAULT '[]'::jsonb,
    application_number TEXT,
    spl_set_id TEXT,
    substance_name TEXT,
    pharm_class JSONB,
    match_method TEXT NOT NULL,
    match_status TEXT NOT NULL,
    payload JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pharma_intelligence.drug_documents (
    document_id TEXT PRIMARY KEY,
    product_key TEXT NOT NULL REFERENCES pharma_intelligence.drug_products(product_key) ON DELETE CASCADE,
    brand_name TEXT,
    generic_name TEXT,
    manufacturer_name TEXT,
    section_names JSONB NOT NULL,
    narrative_text TEXT NOT NULL,
    source TEXT NOT NULL,
    source_identifier TEXT,
    payload JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pharma_intelligence.drug_embeddings (
    embedding_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES pharma_intelligence.drug_documents(document_id) ON DELETE CASCADE,
    product_key TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    model_name TEXT NOT NULL,
    document_content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_index, model_name)
);

CREATE TABLE IF NOT EXISTS pharma_intelligence.investigations (
    investigation_id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    question TEXT NOT NULL,
    summary TEXT NOT NULL,
    scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN ('open','completed','archived')),
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pharma_intelligence.investigation_findings (
    finding_id UUID PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES pharma_intelligence.investigations(investigation_id) ON DELETE CASCADE,
    finding_type TEXT NOT NULL,
    finding_text TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pharma_intelligence.analyst_notes (
    note_id UUID PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES pharma_intelligence.investigations(investigation_id) ON DELETE CASCADE,
    note_text TEXT NOT NULL,
    author TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pharma_intelligence.follow_up_actions (
    action_id UUID PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES pharma_intelligence.investigations(investigation_id) ON DELETE CASCADE,
    action_text TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('low','medium','high')),
    status TEXT NOT NULL CHECK (status IN ('open','completed','cancelled')),
    due_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS drug_documents_product_idx ON pharma_intelligence.drug_documents(product_key);
CREATE INDEX IF NOT EXISTS drug_embeddings_document_idx ON pharma_intelligence.drug_embeddings(document_id);
CREATE INDEX IF NOT EXISTS drug_embeddings_embedding_hnsw_idx ON pharma_intelligence.drug_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS investigations_created_idx ON pharma_intelligence.investigations(created_at DESC);
CREATE INDEX IF NOT EXISTS follow_up_actions_status_idx ON pharma_intelligence.follow_up_actions(status, created_at DESC);

