import pytest

from pageindex.core.utils import pdf_reader


def test_extract_tables_with_pdfplumber_real_fixture_regression():
    pytest.importorskip("pdfplumber")

    pdf_path = "/Users/huangzhenxi/GitLab/OmniX/PageIndex/tests/fixtures/pdfs/q1-fy25-earnings.pdf"
    tables_by_page = pdf_reader._extract_tables_with_pdfplumber(pdf_path, model="gpt-test")

    assert tables_by_page
    first_page, tables = next(iter(sorted(tables_by_page.items())))
    assert first_page >= 1
    assert tables[0]["engine"] == "pdfplumber"
    assert "| " in tables[0]["markdown"]
