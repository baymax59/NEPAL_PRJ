"""Split cleaned page text into overlapping passages ("chunks") that remember their pages.

Chunks are the unit of search: keyword search (Step 5) and embeddings (Step 6) both work on
them, and each result can cite "pages X-Y" of the source document.

- Chunks are built from whole sentences, up to about TARGET_WORDS words.
- The last few sentences of a chunk are repeated at the start of the next one, so a passage
  that straddles a boundary is still found as a whole.
- A very long "sentence" (tables, lists, unpunctuated text) is cut into pieces first, so no
  chunk is much longer than the embedding model can read (~512 tokens).
"""

import re
from dataclasses import dataclass

TARGET_WORDS = 300
OVERLAP_WORDS = 50
MAX_PIECE_WORDS = 250

# Split after sentence-ending punctuation followed by whitespace. Over-splitting at
# abbreviations ("v.", "S.C.R.") is harmless: it only adds possible chunk boundaries.
SENTENCE_BREAK = re.compile(r"(?<=[.?!;])\s+")


@dataclass
class Chunk:
    index: int
    text: str
    page_start: int | None
    page_end: int | None
    word_count: int


@dataclass
class _Piece:
    page: int | None
    words: list[str]


def _pieces(pages: list[tuple[int | None, str]]) -> list[_Piece]:
    pieces = []
    for page, text in pages:
        for sentence in SENTENCE_BREAK.split(text):
            words = sentence.split()
            for i in range(0, len(words), MAX_PIECE_WORDS):
                pieces.append(_Piece(page, words[i : i + MAX_PIECE_WORDS]))
    return pieces


def _make_chunk(index: int, pieces: list[_Piece]) -> Chunk:
    words = [w for p in pieces for w in p.words]
    return Chunk(
        index=index,
        text=" ".join(words),
        page_start=pieces[0].page,
        page_end=pieces[-1].page,
        word_count=len(words),
    )


def chunk_pages(pages: list[tuple[int | None, str]]) -> list[Chunk]:
    """pages: (page_number or None, cleaned text) in reading order."""
    chunks: list[Chunk] = []
    current: list[_Piece] = []
    words_in_current = 0
    has_new_text = False  # False while `current` holds only the overlap carried from the last chunk

    for piece in _pieces(pages):
        if has_new_text and words_in_current + len(piece.words) > TARGET_WORDS:
            chunks.append(_make_chunk(len(chunks), current))
            carried: list[_Piece] = []
            carried_words = 0
            for previous in reversed(current):
                if carried_words + len(previous.words) > OVERLAP_WORDS:
                    break
                carried.insert(0, previous)
                carried_words += len(previous.words)
            current, words_in_current, has_new_text = carried, carried_words, False

        current.append(piece)
        words_in_current += len(piece.words)
        has_new_text = True

    if has_new_text:
        chunks.append(_make_chunk(len(chunks), current))
    return chunks
