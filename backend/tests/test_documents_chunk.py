"""Splitting page text into overlapping, page-aware chunks."""

from app.documents.chunk import MAX_PIECE_WORDS, OVERLAP_WORDS, TARGET_WORDS, chunk_pages


def sentence(n: int) -> str:
    return f"This is sentence number {n} of the test document text."  # 10 words


def page_of_sentences(first: int, count: int) -> str:
    return " ".join(sentence(n) for n in range(first, first + count))


def test_no_text_gives_no_chunks():
    assert chunk_pages([]) == []
    assert chunk_pages([(1, "")]) == []


def test_short_text_is_a_single_chunk_with_its_page():
    [chunk] = chunk_pages([(4, page_of_sentences(0, 3))])

    assert chunk.index == 0
    assert (chunk.page_start, chunk.page_end) == (4, 4)
    assert chunk.word_count == 30


def test_chunks_stay_within_the_target_size():
    chunks = chunk_pages([(1, page_of_sentences(0, 200))])  # 2,000 words

    assert len(chunks) > 1
    assert all(c.word_count <= TARGET_WORDS for c in chunks)


def test_consecutive_chunks_overlap():
    chunks = chunk_pages([(1, page_of_sentences(0, 100))])

    for previous, following in zip(chunks, chunks[1:]):
        before, after = previous.text.split(), following.text.split()
        # Longest run of words that ends `previous` and starts `following`.
        overlap = max(k for k in range(len(before) + 1) if before[len(before) - k :] == after[:k])
        assert 0 < overlap <= OVERLAP_WORDS


def test_every_sentence_ends_up_in_a_chunk():
    chunks = chunk_pages([(1, page_of_sentences(0, 120))])
    all_text = " ".join(c.text for c in chunks)

    assert all(sentence(n) in all_text for n in range(120))


def test_page_ranges_follow_the_text():
    pages = [(1, page_of_sentences(0, 20)), (2, page_of_sentences(20, 20)), (3, page_of_sentences(40, 20))]

    chunks = chunk_pages(pages)

    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 3
    assert any(c.page_start == 1 and c.page_end == 2 for c in chunks)  # a chunk crossing a page break
    for chunk in chunks:
        assert chunk.page_start <= chunk.page_end


def test_text_without_punctuation_is_still_split():
    chunks = chunk_pages([(1, " ".join(f"word{i}" for i in range(1000)))])

    assert all(c.word_count <= MAX_PIECE_WORDS + OVERLAP_WORDS for c in chunks)
    assert sum(1 for c in chunks for w in c.text.split() if w == "word999") == 1


def test_documents_without_page_numbers_keep_none():
    [chunk] = chunk_pages([(None, page_of_sentences(0, 2))])

    assert (chunk.page_start, chunk.page_end) == (None, None)
