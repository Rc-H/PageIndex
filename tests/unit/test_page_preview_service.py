from pathlib import Path

from pageindex.core.services import page_preview_service


class _FakePixmap:
    def __init__(self, page_no: int):
        self._page_no = page_no

    def tobytes(self, fmt: str) -> bytes:
        assert fmt == "png"
        return f"page-{self._page_no}".encode()


class _FakePage:
    def __init__(self, number: int):
        self.number = number

    def get_pixmap(self, matrix, alpha: bool):
        del matrix
        assert alpha is False
        return _FakePixmap(self.number + 1)


class _FakeDocument:
    def __init__(self):
        self.page_count = 3
        self.loaded_indices: list[int] = []
        self.closed = False

    def load_page(self, index: int):
        self.loaded_indices.append(index)
        return _FakePage(index)

    def close(self):
        self.closed = True


class _FakeMuPdf:
    def __init__(self, document: _FakeDocument):
        self._document = document

    @staticmethod
    def Matrix(x: float, y: float):
        return (x, y)

    def open(self, path: str):
        assert path.endswith("sample.pdf")
        return self._document


def test_generate_uses_physical_page_numbers(monkeypatch):
    fake_document = _FakeDocument()
    monkeypatch.setattr(page_preview_service, "pymupdf", _FakeMuPdf(fake_document))

    uploaded: list[tuple[bytes, str, str]] = []

    def _upload(content: bytes, filename: str, content_type: str):
        uploaded.append((content, filename, content_type))
        return f"attachment-{len(uploaded)}"

    monkeypatch.setattr(page_preview_service, "upload_attachment_bytes", _upload)

    service = page_preview_service.PdfPagePreviewService(dpi=144)
    previews = service.generate(Path("/tmp/sample.pdf"))

    assert fake_document.loaded_indices == [0, 1, 2]
    assert fake_document.closed is True
    assert [item[1] for item in uploaded] == [
        "sample-page-1.png",
        "sample-page-2.png",
        "sample-page-3.png",
    ]
    assert previews == [
        {"page_no": 1, "attachment_id": "attachment-1"},
        {"page_no": 2, "attachment_id": "attachment-2"},
        {"page_no": 3, "attachment_id": "attachment-3"},
    ]
