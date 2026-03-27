from pageindex.core.indexers.pipeline.step_01_outline_discovery import word_tables


def test_extract_table_text_formats_field_definition_table():
    table = type(
        "_Table",
        (),
        {
            "rows": [
                type("_Row", (), {"cells": [object(), object(), object(), object()]}),
                type("_Row", (), {"cells": [object(), object(), object(), object()]}),
                type("_Row", (), {"cells": [object(), object(), object(), object()]}),
            ]
        },
    )()

    values = iter(
        [
            "分类", "字段名称", "类型", "说明",
            "基本信息", "核算组织", "组织", "当前核算组织",
            "", "编码", "文本", "自动带出；系统生成",
        ]
    )

    assert word_tables.extract_table_text(
        table,
        lambda cell, image_cache=None: next(values),
    ) == (
        "## 基本信息\n\n"
        "### 核算组织\n"
        "- 类型：组织\n"
        "- 说明：当前核算组织\n\n"
        "### 编码\n"
        "- 类型：文本\n"
        "- 说明：\n"
        "  - 自动带出；\n"
        "  - 系统生成"
    )


def test_extract_table_text_falls_back_to_plain_rows():
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
