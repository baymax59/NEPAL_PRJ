"""Choosing and describing the passages shown for a matched case (search results and explanations)."""

from itertools import zip_longest

from app.schemas.search import Passage
from app.search.keyword import ChunkSnippet


def interleave(semantic_ids: list[int], keyword_ids: list[int], limit: int) -> list[int]:
    """Alternate the best meaning-based and keyword passages, without repeats."""
    chosen: list[int] = []
    for pair in zip_longest(semantic_ids, keyword_ids):
        for chunk_id in pair:
            if chunk_id is not None and chunk_id not in chosen and len(chosen) < limit:
                chosen.append(chunk_id)
    return chosen


def to_passage(chunk_id: int, snippet: ChunkSnippet, semantic_ids: set[int]) -> Passage:
    matched_by = (["keyword"] if snippet.contains_terms else []) + (["semantic"] if chunk_id in semantic_ids else [])
    return Passage(
        chunk_id=chunk_id,
        document_id=snippet.document_id,
        page_start=snippet.page_start,
        page_end=snippet.page_end,
        snippet=snippet.parts,
        matched_by=matched_by,
        similarity=snippet.similarity,
    )
