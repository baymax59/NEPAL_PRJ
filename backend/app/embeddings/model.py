"""Turn text into embedding vectors (lists of 384 numbers) that capture meaning.

Texts with similar meaning get vectors pointing in similar directions, even with different
wording. Vectors are normalised, so cosine similarity is between -1 and 1 (higher = closer).

The model runs locally: case text is never sent to an outside service.
"""

import logging
import threading
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.db.models import EMBEDDING_DIM

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    model_name: str
    # Passages less similar than this to a query are treated as unrelated. Model-specific:
    # each model spreads its similarity values differently.
    min_similarity: float
    # The same for passage-to-passage comparison (a whole document as the query).
    min_passage_similarity: float

    def embed_query(self, text: str) -> list[float]:
        """A short search query, matched against passages."""

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Passages of documents (stored chunks, or chunks of an uploaded case)."""


class SentenceTransformerEmbedder:
    # BGE models retrieve better when short queries carry this instruction; passages don't.
    QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

    def __init__(
        self,
        model_name: str,
        cache_dir: Path,
        *,
        allow_download: bool,
        min_similarity: float,
        min_passage_similarity: float,
    ):
        # Imported here: loading PyTorch takes seconds and isn't needed for keyword search.
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(
            model_name, cache_folder=str(cache_dir), device="cpu", local_files_only=not allow_download
        )
        dimension = self.model.get_embedding_dimension()
        if dimension != EMBEDDING_DIM:
            raise RuntimeError(
                f"{model_name} produces {dimension}-dimensional vectors, but the database stores "
                f"{EMBEDDING_DIM}. Changing models needs a migration."
            )
        self.model_name = model_name
        self.min_similarity = min_similarity
        self.min_passage_similarity = min_passage_similarity

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(self.QUERY_INSTRUCTION + text, normalize_embeddings=True).tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False).tolist()


_embedder: SentenceTransformerEmbedder | None = None
_lock = threading.Lock()


def load_embedder(*, allow_download: bool = False) -> SentenceTransformerEmbedder:
    """Load the model once per process. The API never downloads: run scripts.embed_chunks first."""
    global _embedder
    with _lock:
        if _embedder is None:
            settings = get_settings()
            _embedder = SentenceTransformerEmbedder(
                settings.embedding_model,
                settings.model_cache_dir,
                allow_download=allow_download,
                min_similarity=settings.semantic_min_similarity,
                min_passage_similarity=settings.similar_passage_min_similarity,
            )
    return _embedder


def get_embedder() -> Embedder | None:
    """FastAPI dependency. None if the model isn't available: search then falls back to keywords."""
    try:
        return load_embedder()
    except Exception:
        logger.warning("Embedding model not available; semantic search disabled", exc_info=True)
        return None
