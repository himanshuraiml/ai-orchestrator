import uuid

from orchestrator.context.assembler import assemble_context
from orchestrator.context.chunker import count_tokens
from orchestrator.context.retriever import RetrievedChunk


def _chunk(content: str, distance: float = 0.1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=content,
        chunk_index=0,
        distance=distance,
        metadata={},
    )


def test_empty_chunks_produce_empty_context():
    result = assemble_context([], token_budget=1000)
    assert result.text == ""
    assert result.chunk_ids == []
    assert result.token_count == 0
    assert result.truncated is False


def test_all_chunks_fit_within_budget():
    chunks = [_chunk("short chunk one"), _chunk("short chunk two")]
    result = assemble_context(chunks, token_budget=1000)

    assert len(result.chunk_ids) == 2
    assert result.truncated is False
    assert "short chunk one" in result.text
    assert "short chunk two" in result.text


def test_stops_before_exceeding_budget():
    big_chunk = _chunk("word " * 200)  # ~200 tokens
    small_chunk = _chunk("tiny")

    budget = count_tokens(big_chunk.content)  # exactly enough for big, none left for small
    result = assemble_context([big_chunk, small_chunk], token_budget=budget)

    assert result.chunk_ids == [big_chunk.chunk_id]
    assert result.token_count <= budget
    assert result.truncated is True


def test_skips_oversized_chunk_but_keeps_smaller_ones_that_fit():
    too_big = _chunk("word " * 5000)
    fits = _chunk("small chunk that fits")

    result = assemble_context([too_big, fits], token_budget=100)

    assert too_big.chunk_id not in result.chunk_ids
    assert fits.chunk_id in result.chunk_ids
    assert result.truncated is True
