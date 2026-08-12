import tiktoken

from orchestrator.context.chunker import chunk_text, count_tokens

_ENCODING = tiktoken.get_encoding("cl100k_base")


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_is_a_single_chunk():
    text = "This is a short paragraph that easily fits in one chunk."
    chunks = chunk_text(text, chunk_size=512, overlap=64)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_splits_on_paragraph_boundaries_when_over_budget():
    paragraphs = [f"Paragraph {i} " + ("word " * 100) for i in range(10)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, chunk_size=100, overlap=10)

    assert len(chunks) > 1
    for chunk in chunks:
        assert count_tokens(chunk) <= 110  # small slack for the overlap prefix


def test_consecutive_chunks_overlap():
    # BPE re-tokenization at a decoded chunk boundary isn't guaranteed to
    # reproduce the exact original token IDs, so this checks the overlap
    # *effect* (chunks collectively cover more tokens than the source text
    # once because content is repeated across the cut) rather than an exact
    # token-ID match.
    paragraphs = [f"Paragraph number {i}." + (" filler" * 30) for i in range(6)]
    text = "\n\n".join(paragraphs)

    chunks_no_overlap = chunk_text(text, chunk_size=60, overlap=0)
    chunks_with_overlap = chunk_text(text, chunk_size=60, overlap=15)

    assert len(chunks_with_overlap) >= 2
    total_no_overlap = sum(count_tokens(c) for c in chunks_no_overlap)
    total_with_overlap = sum(count_tokens(c) for c in chunks_with_overlap)
    assert total_with_overlap > total_no_overlap


def test_oversized_paragraph_is_hard_split():
    huge_paragraph = "word " * 2000  # single paragraph, no \n\n, way over budget
    chunks = chunk_text(huge_paragraph, chunk_size=512, overlap=64)

    assert len(chunks) > 1
    for chunk in chunks:
        assert count_tokens(chunk) <= 512
