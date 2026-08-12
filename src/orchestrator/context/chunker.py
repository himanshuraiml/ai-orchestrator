"""Semantic chunker — arch doc §27-28 / tasks.md 4.2.

Packs paragraphs into token-budgeted windows (default 512 tokens, 64-token
overlap) rather than cutting text at a hard character offset, so chunks
tend to stay on paragraph boundaries. A paragraph longer than the chunk
size on its own is hard-split by tokens as a fallback.
"""

import tiktoken

DEFAULT_CHUNK_SIZE = 512
DEFAULT_OVERLAP = 64

_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _hard_split(tokens: list[int], chunk_size: int) -> list[list[int]]:
    return [tokens[i : i + chunk_size] for i in range(0, len(tokens), chunk_size)]


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Splits `text` into chunks of at most `chunk_size` tokens, each
    (after the first) starting with the trailing `overlap` tokens of the
    previous chunk for retrieval continuity across the cut."""
    if not text.strip():
        return []

    paragraphs = _split_paragraphs(text)
    chunks: list[list[int]] = []
    current: list[int] = []

    for paragraph in paragraphs:
        paragraph_tokens = _ENCODING.encode(paragraph + "\n\n")

        if len(paragraph_tokens) > chunk_size:
            if current:
                chunks.append(current)
                current = []
            chunks.extend(_hard_split(paragraph_tokens, chunk_size))
            continue

        if current and len(current) + len(paragraph_tokens) > chunk_size:
            chunks.append(current)
            current = current[-overlap:] if overlap else []

        current.extend(paragraph_tokens)

    if current:
        chunks.append(current)

    return [_ENCODING.decode(chunk).strip() for chunk in chunks if chunk]
