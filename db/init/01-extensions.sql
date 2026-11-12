-- Runs once when the database volume is first created.
-- pgvector stores embeddings and runs similarity search inside PostgreSQL.
CREATE EXTENSION IF NOT EXISTS vector;
