"""Embedding stored chunks (embed_pending_chunks), using FakeEmbedder."""

import pytest
from sqlalchemy import select, update

from app.db.models import EMBEDDING_DIM, Case, DocumentChunk
from app.embeddings.indexing import embed_pending_chunks


def quiet(_message: str) -> None:
    pass


def forget_embeddings(session) -> None:
    session.execute(update(DocumentChunk).values(embedding=None, embedding_model=None))
    session.execute(update(Case).values(processing_status="text_extracted"))


def test_chunks_without_embeddings_are_embedded_and_the_case_marked_indexed(db_session, add_case, fake_embedder):
    case = add_case(1, title="X", year=2023, passages=["First passage text.", "Second passage text."])
    forget_embeddings(db_session)

    count = embed_pending_chunks(db_session, fake_embedder, progress=quiet)

    rows = db_session.execute(select(DocumentChunk.embedding, DocumentChunk.embedding_model)).all()
    assert count == 2
    assert all(model == fake_embedder.model_name and len(vector) == EMBEDDING_DIM for vector, model in rows)
    db_session.refresh(case)
    assert case.processing_status == "indexed"


def test_nothing_is_redone_when_everything_is_embedded(db_session, add_case, fake_embedder):
    add_case(1, title="X", year=2023, passages=["Some passage."])

    assert embed_pending_chunks(db_session, fake_embedder, progress=quiet) == 0


def test_switching_models_re_embeds_every_chunk(db_session, add_case, fake_embedder):
    add_case(1, title="X", year=2023, passages=["One.", "Two.", "Three."])
    other_model = type(fake_embedder)()
    other_model.model_name = "another-model"

    assert embed_pending_chunks(db_session, other_model, progress=quiet) == 3


def test_an_interrupted_run_leaves_the_case_unindexed_and_can_be_resumed(db_session, add_case, fake_embedder):
    case = add_case(1, title="X", year=2023, passages=["One.", "Two."])
    forget_embeddings(db_session)

    class CrashesOnSecondBatch(type(fake_embedder)):
        calls = 0

        def embed_passages(self, texts):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("model crashed")
            return super().embed_passages(texts)

    with pytest.raises(RuntimeError):
        embed_pending_chunks(db_session, CrashesOnSecondBatch(), batch_size=1, progress=quiet)
    db_session.refresh(case)
    assert case.processing_status == "text_extracted"  # one chunk still missing

    assert embed_pending_chunks(db_session, fake_embedder, progress=quiet) == 1  # only the missing one
    db_session.refresh(case)
    assert case.processing_status == "indexed"
