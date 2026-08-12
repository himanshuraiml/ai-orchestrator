"""OCR MCP server — PyMuPDF text-layer fast path + PaddleOCR, arch doc §24 /
tasks.md 2.2.3.

Extracts text directly from a PDF's text layer where present (free,
instant); falls back to rasterizing + PaddleOCR for pages with no
extractable text (i.e. scanned pages). Plain images always go through
PaddleOCR. PaddleOCR replaces Tesseract as the recognition backend per
user direction — meaningfully more accurate, and its models were already
cached locally from an earlier project (~/.paddlex/official_models).
"""

import tempfile
from pathlib import Path

# `pymupdf` is the current import name; the legacy `fitz` alias prints a
# deprecation warning to *stdout*, which corrupts the MCP stdio JSON-RPC
# stream, so it must not be used here.
import pymupdf as fitz
from mcp.server.mcpserver import MCPServer
from paddleocr import PaddleOCR

mcp = MCPServer("ocr")

_IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "tiff", "bmp"}

# Loaded lazily (and once per server process) since construction loads
# several model weights from disk — not worth paying that cost for calls
# that hit the free text-layer fast path.
_engines: dict[str, PaddleOCR] = {}


def _engine(language: str) -> PaddleOCR:
    if language not in _engines:
        _engines[language] = PaddleOCR(use_textline_orientation=True, lang=language)
    return _engines[language]


def _ocr_image_file(path: str, language: str) -> str:
    lines: list[str] = []
    for page in _engine(language).predict(path):
        lines.extend(page.json["res"]["rec_texts"])
    return "\n".join(lines)


def _ocr_page(page: fitz.Page, language: str, workdir: Path) -> str:
    pixmap = page.get_pixmap(dpi=300)
    image_path = workdir / f"page-{page.number}.png"
    pixmap.save(image_path)
    return _ocr_image_file(str(image_path), language)


@mcp.tool()
def extract_text(file_path: str, language: str = "en") -> dict:
    """Extract text from a PDF or image, OCR-ing scanned pages with PaddleOCR."""
    suffix = file_path.lower().rsplit(".", 1)[-1]

    if suffix in _IMAGE_SUFFIXES:
        text = _ocr_image_file(file_path, language)
        return {"text": text, "pages": 1, "ocr_pages": [0], "method": "ocr"}

    doc = fitz.open(file_path)
    parts: list[str] = []
    ocr_pages: list[int] = []

    try:
        with tempfile.TemporaryDirectory(prefix="orch-ocr-") as workdir:
            for index, page in enumerate(doc):
                text = page.get_text().strip()
                if text:
                    parts.append(text)
                else:
                    parts.append(_ocr_page(page, language, Path(workdir)))
                    ocr_pages.append(index)
    finally:
        doc.close()

    if ocr_pages and len(ocr_pages) == len(parts):
        method = "ocr"
    elif ocr_pages:
        method = "mixed"
    else:
        method = "text_layer"

    return {
        "text": "\n\n".join(parts),
        "pages": len(parts),
        "ocr_pages": ocr_pages,
        "method": method,
    }


if __name__ == "__main__":
    mcp.run()
