-- Adds real pgvector support for legal_corpus_chunks, sized for
-- OpenRouter's baai/bge-m3 embedding model (1024 dimensions).
--
-- NOTE: no working pgvector column/RPC existed before this migration —
-- the previous code referenced `embedding_vertex` / `match_legal_corpus_vertex`,
-- neither of which appear anywhere in the migration history.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE public.legal_corpus_chunks
  ADD COLUMN embedding_openrouter vector(1024);

-- Approximate nearest-neighbour index for cosine similarity search.
-- (lists=100 is a reasonable default for small-to-medium corpora; raise it
-- as the table grows past a few hundred thousand rows.)
CREATE INDEX idx_corpus_embedding_openrouter
  ON public.legal_corpus_chunks
  USING ivfflat (embedding_openrouter vector_cosine_ops)
  WITH (lists = 100);

-- RLS-safe similarity search, scoped to the calling user's own documents.
CREATE OR REPLACE FUNCTION public.match_legal_corpus_openrouter(
  query_embedding vector(1024),
  match_user_id UUID,
  match_count INT DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  document_id UUID,
  chunk_index INT,
  content TEXT,
  similarity FLOAT
)
LANGUAGE sql STABLE SET search_path = public AS $$
  SELECT
    id,
    document_id,
    chunk_index,
    content,
    1 - (embedding_openrouter <=> query_embedding) AS similarity
  FROM public.legal_corpus_chunks
  WHERE user_id = match_user_id
    AND embedding_openrouter IS NOT NULL
  ORDER BY embedding_openrouter <=> query_embedding
  LIMIT match_count;
$$;

REVOKE EXECUTE ON FUNCTION public.match_legal_corpus_openrouter FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.match_legal_corpus_openrouter TO authenticated, service_role;

-- The old JSONB `embedding` column is left in place untouched — it was never
-- populated by any working code path, so there's nothing to migrate off it.
-- Drop it later once you've confirmed nothing else references it:
--   ALTER TABLE public.legal_corpus_chunks DROP COLUMN embedding;
