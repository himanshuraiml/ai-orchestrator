import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.context.embeddings import EmbeddingProvider
from orchestrator.context.manager import ContextManager, UnknownArtifactError
from orchestrator.tools.adapters.base import ToolAdapter


class _FakeEmbedder(EmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class _FakeAdapter(ToolAdapter):
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def invoke(self, arguments: dict) -> dict:
        self.calls.append(arguments)
        return self.response


@pytest.fixture
def manager():
    return ContextManager(
        embedder=_FakeEmbedder(),
        ocr_adapter=_FakeAdapter({"text": "extracted pdf text", "method": "text_layer", "pages": 1}),
        pandoc_adapter=_FakeAdapter({"success": True}),
    )


async def test_ingest_file_routes_pdf_through_ocr_adapter(manager, tmp_path):
    pdf_path = tmp_path / "input.pdf"
    pdf_path.write_bytes(b"%PDF-fake")

    artifact_id = uuid.uuid4()
    fake_artifact = type("Artifact", (), {"storage_uri": str(pdf_path)})()

    with (
        patch("orchestrator.context.manager.artifacts_repo.get_artifact", AsyncMock(return_value=fake_artifact)),
        patch(
            "orchestrator.context.manager.documents_repo.create_document",
            AsyncMock(return_value=type("Document", (), {"id": uuid.uuid4()})()),
        ) as create_doc,
        patch("orchestrator.context.manager.documents_repo.create_chunks", AsyncMock()) as create_chunks,
    ):
        await manager.ingest_file(session=AsyncMock(), artifact_id=artifact_id)

    assert manager.ocr_adapter.calls == [{"file_path": str(pdf_path)}]
    assert create_doc.call_args.kwargs["parser"] == "ocr:text_layer"
    assert create_chunks.call_args.kwargs["chunks"] == ["extracted pdf text"]


async def test_ingest_file_routes_plain_text_without_any_adapter(manager, tmp_path):
    text_path = tmp_path / "notes.txt"
    text_path.write_text("plain notes content")

    fake_artifact = type("Artifact", (), {"storage_uri": str(text_path)})()

    with (
        patch("orchestrator.context.manager.artifacts_repo.get_artifact", AsyncMock(return_value=fake_artifact)),
        patch(
            "orchestrator.context.manager.documents_repo.create_document",
            AsyncMock(return_value=type("Document", (), {"id": uuid.uuid4()})()),
        ) as create_doc,
        patch("orchestrator.context.manager.documents_repo.create_chunks", AsyncMock()),
    ):
        await manager.ingest_file(session=AsyncMock(), artifact_id=uuid.uuid4())

    assert manager.ocr_adapter.calls == []
    assert manager.pandoc_adapter.calls == []
    assert create_doc.call_args.kwargs["parser"] == "plain_text"


async def test_ingest_file_routes_docx_through_pandoc_adapter(manager, tmp_path):
    docx_path = tmp_path / "report.docx"
    docx_path.write_bytes(b"fake docx bytes")

    def convert_and_write(arguments):
        Path(arguments["output_path"]).write_text("converted markdown text")
        return {"success": True}

    manager.pandoc_adapter.invoke = AsyncMock(side_effect=lambda args: convert_and_write(args))

    fake_artifact = type("Artifact", (), {"storage_uri": str(docx_path)})()

    with (
        patch("orchestrator.context.manager.artifacts_repo.get_artifact", AsyncMock(return_value=fake_artifact)),
        patch(
            "orchestrator.context.manager.documents_repo.create_document",
            AsyncMock(return_value=type("Document", (), {"id": uuid.uuid4()})()),
        ) as create_doc,
        patch("orchestrator.context.manager.documents_repo.create_chunks", AsyncMock()),
    ):
        await manager.ingest_file(session=AsyncMock(), artifact_id=uuid.uuid4())

    assert create_doc.call_args.kwargs["parser"] == "pandoc:markdown"
    assert create_doc.call_args.kwargs["extracted_text"] == "converted markdown text"


async def test_ingest_file_raises_for_unknown_artifact(manager):
    with (
        patch("orchestrator.context.manager.artifacts_repo.get_artifact", AsyncMock(return_value=None)),
        pytest.raises(UnknownArtifactError),
    ):
        await manager.ingest_file(session=AsyncMock(), artifact_id=uuid.uuid4())
