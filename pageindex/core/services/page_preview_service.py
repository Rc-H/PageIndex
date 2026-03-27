from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pageindex.core.utils.image_upload import upload_attachment_bytes

try:
    import pymupdf
except ImportError:  # pragma: no cover - optional dependency
    pymupdf = None


@dataclass(frozen=True)
class PdfPagePreview:
    page_no: int
    attachment_id: str


class PdfPagePreviewService:
    def __init__(self, dpi: int = 144):
        self._dpi = dpi

    def generate(self, file_path: Path) -> list[dict[str, str | int]]:
        if not self._should_generate(file_path):
            return []

        mupdf = self._require_pymupdf()
        document = mupdf.open(str(file_path))
        scale = self._dpi / 72.0
        matrix = mupdf.Matrix(scale, scale)

        try:
            previews: list[dict[str, str | int]] = []
            stem = file_path.stem or "document"
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                page_no = page.number + 1
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                attachment_id = upload_attachment_bytes(
                    pixmap.tobytes("png"),
                    filename=f"{stem}-page-{page_no}.png",
                    content_type="image/png",
                )
                if attachment_id:
                    previews.append(
                        {
                            "page_no": page_no,
                            "attachment_id": attachment_id,
                        }
                    )
            return previews
        finally:
            document.close()

    @staticmethod
    def _should_generate(file_path: Path) -> bool:
        return file_path.suffix.lower() == ".pdf"

    @staticmethod
    def _require_pymupdf():
        if pymupdf is None:
            raise RuntimeError("pymupdf is required for PDF page preview generation")
        return pymupdf
