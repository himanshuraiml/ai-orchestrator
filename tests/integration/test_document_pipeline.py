"""tasks.md 2.5.2 — upload PDF → OCR → parse → Pandoc → DOCX, exercised
through the real MCP servers (subprocess round-trip), not mocks. Skipped
when the local binaries/model weights this depends on aren't available, so
it stays portable across machines.
"""

import shutil
from pathlib import Path

import pymupdf
import pytest

from orchestrator.tools.adapters.ocr import OCRAdapter
from orchestrator.tools.adapters.pandoc import PandocAdapter

pytestmark = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc binary not installed")


def _make_pdf_with_text(path: Path, text: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


async def test_pdf_to_ocr_to_docx_pipeline(tmp_path: Path):
    pdf_path = tmp_path / "input.pdf"
    _make_pdf_with_text(pdf_path, "Hello from the Phase 2 pipeline test.")

    ocr_result = await OCRAdapter().invoke({"file_path": str(pdf_path)})
    assert "Hello from the Phase 2 pipeline test." in ocr_result["text"]
    assert ocr_result["method"] == "text_layer"

    markdown_path = tmp_path / "extracted.md"
    markdown_path.write_text(f"# Extracted\n\n{ocr_result['text']}\n")

    docx_path = tmp_path / "output.docx"
    convert_result = await PandocAdapter().invoke(
        {"input_path": str(markdown_path), "output_path": str(docx_path)}
    )

    assert convert_result["success"]
    assert docx_path.exists()
    assert docx_path.stat().st_size > 0
