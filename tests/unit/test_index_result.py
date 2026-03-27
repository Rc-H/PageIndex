from pageindex.core.indexers.pipeline.step_06_finalize.result import build_index_result


def test_build_index_result_includes_optional_extract_and_stats():
    result = build_index_result(
        doc_name="sample",
        structure=[{"title": "Intro"}],
        doc_description="summary",
        page_count=3,
        char_count=120,
        token_count=40,
        extract={"blocks": [{"block_no": 1}]},
    )

    assert result == {
        "doc_name": "sample",
        "structure": [{"title": "Intro"}],
        "doc_description": "summary",
        "page_count": 3,
        "char_count": 120,
        "token_count": 40,
        "extract": {"blocks": [{"block_no": 1}]},
    }
