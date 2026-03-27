from pageindex.core.indexers.pipeline.step_01_outline_discovery.step_04_outline_index_alignment import alignment


def test_add_page_number_to_toc_collects_single_item_results(monkeypatch):
    monkeypatch.setattr(alignment, "load_prompt", lambda _: "prompt")

    responses = iter(
        [
            '{"structure":"1","title":"Intro","physical_index":"<physical_index_3>"}',
            '{"structure":"2","title":"Body","physical_index":null}',
        ]
    )
    monkeypatch.setattr(alignment, "call_llm", lambda **kwargs: next(responses))

    result = alignment.add_page_number_to_toc(
        "partial-doc",
        [{"structure": "1", "title": "Intro"}, {"structure": "2", "title": "Body"}],
        model="demo",
    )

    assert result == [
        {"structure": "1", "title": "Intro", "physical_index": 3},
        {"structure": "2", "title": "Body", "physical_index": None},
    ]


def test_add_page_number_to_toc_preserves_input_identity_when_model_omits_fields(monkeypatch):
    monkeypatch.setattr(alignment, "load_prompt", lambda _: "prompt")
    monkeypatch.setattr(alignment, "call_llm", lambda **kwargs: '{"physical_index":"<physical_index_9>"}')

    result = alignment.add_page_number_to_toc(
        "partial-doc",
        [{"structure": "1.2", "title": "Methods"}],
        model="demo",
    )

    assert result == [
        {"structure": "1.2", "title": "Methods", "physical_index": 9}
    ]
