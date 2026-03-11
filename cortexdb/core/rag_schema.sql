-- RAG Pipeline Schema
-- Document and chunk storage for Retrieval-Augmented Generation

CREATE TABLE IF NOT EXISTS rag_documents (
    doc_id TEXT PRIMARY KEY,
    collection TEXT NOT NULL DEFAULT 'documents',
    chunk_count INT NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    tenant_id TEXT,
    content_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES rag_documents(doc_id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_index INT NOT NULL,
    start_char INT NOT NULL,
    end_char INT NOT NULL,
    token_count INT NOT NULL,
    metadata JSONB DEFAULT '{}',
    tenant_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks (doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_rag_docs_tenant ON rag_documents (tenant_id, collection);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_tenant ON rag_chunks (tenant_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_fts ON rag_chunks USING GIN(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc_tenant ON rag_chunks(doc_id, tenant_id);
