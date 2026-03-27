from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_04_outline_index_alignment import alignment


def test_toc_index_extractor_collects_single_item_results(monkeypatch):
    monkeypatch.setattr(alignment, "load_prompt", lambda _: "prompt")

    responses = iter(
        [
            '{"structure":"1","title":"Intro","page":3}',
            '{"structure":"2","title":"Body","page":null}',
        ]
    )
    monkeypatch.setattr(alignment, "call_llm", lambda **kwargs: next(responses))

    result = alignment.toc_index_extractor(
        [{"structure": "1", "title": "Intro"}, {"structure": "2", "title": "Body"}],
        "toc-pages",
        model="demo",
    )

    assert result == [
        {"structure": "1", "title": "Intro", "page": 3},
        {"structure": "2", "title": "Body", "page": None},
    ]


def test_toc_index_extractor_preserves_input_identity_when_model_omits_fields(monkeypatch):
    monkeypatch.setattr(alignment, "load_prompt", lambda _: "prompt")
    monkeypatch.setattr(alignment, "call_llm", lambda **kwargs: '{"page":9}')

    result = alignment.toc_index_extractor(
        [{"structure": "1.2", "title": "Methods"}],
        "toc-pages",
        model="demo",
    )

    assert result == [
        {"structure": "1.2", "title": "Methods", "page": 9}
    ]
