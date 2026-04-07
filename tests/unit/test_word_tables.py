from pageindex.core.indexers.pipeline.step_01_outline_discovery import word_tables


def test_extract_table_text_renders_plain_rows():
    table = type(
        "_Table",
        (),
        {
            "rows": [
                type("_Row", (), {"cells": [object(), object()]}),
                type("_Row", (), {"cells": [object(), object()]}),
            ]
        },
    )()

    values = iter(["列A", "列B", "值1", "值2"])

    assert word_tables.extract_table_text(
        table,
        lambda cell, image_cache=None: next(values),
    ) == "列A | 列B\n值1 | 值2"


def test_format_plain_table_rows_preserves_empty_middle_cell():
    table = type(
        "_Table",
        (),
        {
            "rows": [
                type("_Row", (), {"cells": [object(), object(), object()]}),
                type("_Row", (), {"cells": [object(), object(), object()]}),
            ]
        },
    )()

    values = iter(["A", "B", "C", "D", "", "F"])

    result = word_tables.extract_table_text(
        table,
        lambda cell, image_cache=None: next(values),
    )

    # Row 1: A | B | C
    # Row 2: D |   | F  ← empty middle cell preserved as empty separator slot
    assert result == "A | B | C\nD |  | F"


def test_format_plain_table_rows_preserves_empty_leading_cell():
    table = type(
        "_Table",
        (),
        {
            "rows": [
                type("_Row", (), {"cells": [object(), object()]}),
                type("_Row", (), {"cells": [object(), object()]}),
            ]
        },
    )()

    values = iter(["A", "B", "", "D"])

    result = word_tables.extract_table_text(
        table,
        lambda cell, image_cache=None: next(values),
    )

    assert result == "A | B\n | D"


def test_format_plain_table_rows_drops_fully_empty_rows():
    table = type(
        "_Table",
        (),
        {
            "rows": [
                type("_Row", (), {"cells": [object(), object()]}),
                type("_Row", (), {"cells": [object(), object()]}),
                type("_Row", (), {"cells": [object(), object()]}),
            ]
        },
    )()

    values = iter(["A", "B", "", "", "C", "D"])

    result = word_tables.extract_table_text(
        table,
        lambda cell, image_cache=None: next(values),
    )

    # Middle row is fully empty → dropped entirely (no blank line in output)
    assert result == "A | B\nC | D"
