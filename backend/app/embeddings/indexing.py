"""Compute and store embeddings for document chunks.

Chunks are (re-)embedded when they have no embedding yet, or were embedded by a different
model, so switching models never mixes incompatible vectors in one search.
"""

from collections.abc import Callable

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.enums import ProcessingStatus
from app.db.models import Case, DocumentChunk
from app.embeddings.model import Embedder


def embed_pending_chunks(
    session: Session,
    embedder: Embedder,
    *,
    batch_size: int = 64,
    progress: Callable[[str], None] = print,
) -> int:
    """Embed every chunk that needs it. Commits after each batch, so it can be resumed."""
    needs_embedding = or_(DocumentChunk.embedding.is_(None), DocumentChunk.embedding_model != embedder.model_name)
    chunk_ids = session.scalars(select(DocumentChunk.id).where(needs_embedding).order_by(DocumentChunk.id)).all()

    for start in range(0, len(chunk_ids), batch_size):
        batch_ids = chunk_ids[start : start + batch_size]
        rows = session.execute(
            select(DocumentChunk.id, DocumentChunk.text).where(DocumentChunk.id.in_(batch_ids))
        ).all()
        vectors = embedder.embed_passages([row.text for row in rows])
        session.execute(
            update(DocumentChunk),
            [
                {"id": row.id, "embedding": vector, "embedding_model": embedder.model_name}
                for row, vector in zip(rows, vectors, strict=True)
            ],
        )
        session.commit()
        progress(f"embedded {min(start + batch_size, len(chunk_ids))}/{len(chunk_ids)}")

    _mark_indexed_cases(session, embedder.model_name)
    return len(chunk_ids)


def _mark_indexed_cases(session: Session, model_name: str) -> None:
    """A case is 'indexed' once all its chunks are embedded with the current model."""
    not_ready = select(DocumentChunk.case_id).where(
        or_(DocumentChunk.embedding.is_(None), DocumentChunk.embedding_model != model_name)
    )
    has_chunks = select(DocumentChunk.case_id)
    session.execute(
        update(Case)
        .where(
            Case.processing_status == ProcessingStatus.TEXT_EXTRACTED.value,
            Case.id.in_(has_chunks),
            Case.id.not_in(not_ready),
        )
        .values(processing_status=ProcessingStatus.INDEXED.value)
    )
    session.commit()
