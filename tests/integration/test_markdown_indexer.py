from pageindex.core.indexers.markdown import (
    extract_node_text_content,
    extract_nodes_from_markdown,
    tree_thinning_for_index,
    update_node_list_with_text_token_count,
)


def test_extract_nodes_from_markdown_ignores_headers_inside_code_blocks():
    markdown = """
# Intro
Text

```python
# not-a-heading
## still-not-a-heading
```

## Real Section
More text
"""
    node_list, _ = extract_nodes_from_markdown(markdown)
    titles = [n["node_title"] for n in node_list]
    assert "not-a-heading" not in titles
    assert "still-not-a-heading" not in titles
    assert "Intro" in titles
    assert "Real Section" in titles
