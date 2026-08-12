"""ContextManager — arch doc §27 / tasks.md 4.1.

Owns the file -> parse -> chunk -> embed -> store pipeline and the
retrieve -> assemble path back out. Parsing reuses the Phase 2 tool
adapters rather than re-implementing extraction: OCRAdapter (PyMuPDF text
layer + PaddleOCR) for PDFs/images, PandocAdapter (-> markdown) for
everything else Pandoc understands, plain read for text/markdown.
"""

import tempfile
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.context.assembler import AssembledContext, assemble_context
from orchestrator.context.chunker import chunk_text
from orchestrator.context.embeddings import EmbeddingProvider
from orchestrator.context.retriever import RetrievedChunk, retrieve_chunks
from orchestrator.db.models import Document
from orchestrator.db.repositories import artifacts as artifacts_repo
from orchestrator.db.repositories import documents as documents_repo
from orchestrator.tools.adapters.base import ToolAdapter

_OCR_SUFFIXES = {"pdf", "png", "jpg", "jpeg", "tiff", "bmp"}
_PLAIN_TEXT_SUFFIXES = {"txt", "md", "markdown"}


class UnknownArtifactError(LookupError):
    pass


class ContextManager:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        ocr_adapter: ToolAdapter,
        pandoc_adapter: ToolAdapter,
    ) -> None:
        self.embedder = embedder
        self.ocr_adapter = ocr_adapter
        self.pandoc_adapter = pandoc_adapter

    async def _extract_text(self, path: Path) -> tuple[str, str, int | None]:
        """Returns (text, parser_used, page_count)."""
        suffix = path.suffix.lower().lstrip(".")

        if suffix in _OCR_SUFFIXES:
            result = await self.ocr_adapter.invoke({"file_path": str(path)})
            return result["text"], f"ocr:{result.get('method', 'unknown')}", result.get("pages")

        if suffix in _PLAIN_TEXT_SUFFIXES:
            return path.read_text(), "plain_text", None

        with tempfile.TemporaryDirectory(prefix="orch-ingest-") as workdir:
            output_path = Path(workdir) / "converted.md"
            result = await self.pandoc_adapter.invoke(
                {"input_path": str(path), "output_path": str(output_path), "to_format": "markdown"}
            )
            if not result.get("success"):
                raise ValueError(f"Failed to parse {path.name!r}: {result.get('error')}")
            return output_path.read_text(), "pandoc:markdown", None

    async def ingest_file(self, session: AsyncSession, artifact_id: uuid.UUID) -> Document:
        """Resolves `artifact_id` to its stored file, parses it, chunks +
        embeds the text, and persists a Document + its DocumentChunks —
        arch doc §27.
        """
        artifact = await artifacts_repo.get_artifact(session, artifact_id)
        if artifact is None:
            raise UnknownArtifactError(f"No artifact with id {artifact_id}")

        text, parser, page_count = await self._extract_text(Path(artifact.storage_uri))

        document = await documents_repo.create_document(
            session,
            artifact_id=artifact_id,
            parser=parser,
            page_count=page_count,
            extracted_text=text,
        )

        chunks = chunk_text(text)
        if chunks:
            embeddings = await self.embedder.embed(chunks)
            await documents_repo.create_chunks(
                session, document_id=document.id, chunks=chunks, embeddings=embeddings
            )

        return document

    async def retrieve(
        self, session: AsyncSession, query: str, *, top_k: int = 10
    ) -> list[RetrievedChunk]:
        [query_embedding] = await self.embedder.embed([query])
        return await retrieve_chunks(session, query_embedding, top_k=top_k)

    async def build_context(
        self, session: AsyncSession, query: str, token_budget: int
    ) -> AssembledContext:
        chunks = await self.retrieve(session, query, top_k=10)
        return assemble_context(chunks, token_budget)
