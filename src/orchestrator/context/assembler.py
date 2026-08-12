"""Token-budget-aware context assembly — arch doc §27-28 / tasks.md 4.5.

Retrieval + reranking already happens upstream (retriever.py returns
chunks ordered by relevance); this just packs whole chunks into the
budget in that order, stopping before the budget would be exceeded so no
chunk is truncated mid-sentence.
"""

import uuid
from dataclasses import dataclass, field

from orchestrator.context.chunker import count_tokens
from orchestrator.context.retriever import RetrievedChunk


@dataclass
class AssembledContext:
    text: str
    chunk_ids: list[uuid.UUID] = field(default_factory=list)
    token_count: int = 0
    truncated: bool = False


def assemble_context(chunks: list[RetrievedChunk], token_budget: int) -> AssembledContext:
    included: list[RetrievedChunk] = []
    used_tokens = 0

    for chunk in chunks:
        chunk_tokens = count_tokens(chunk.content)
        if used_tokens + chunk_tokens > token_budget:
            continue
        included.append(chunk)
        used_tokens += chunk_tokens

    text = "\n\n---\n\n".join(chunk.content for chunk in included)

    return AssembledContext(
        text=text,
        chunk_ids=[chunk.chunk_id for chunk in included],
        token_count=used_tokens,
        truncated=len(included) < len(chunks),
    )
