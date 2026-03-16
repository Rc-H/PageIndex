# PageIndex LLM Prompt 清单

这份清单列出 `PageIndex` 当前代码里所有直接发送给 LLM 的业务 prompt。

说明：

- 这里只统计运行时真实调用的 prompt 模板。
- 不包含 SDK / OpenAI 客户端内部参数包装。
- 这些 prompt 都是以单条 `user` 消息发送；少数“续写”场景会额外带 `chat_history`。
- 模板里的 `{...}` 表示运行时插入的动态变量。

---

## 发送方式

底层发送在：

- [llm.py](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/llm.py)
- [utils.py](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/utils.py)

调用形式有三种：

- `ChatGPT_API(...)`
- `ChatGPT_API_async(...)`
- `ChatGPT_API_with_finish_reason(...)`

---

## `page_index.py`

### 1. `check_title_appearance`

位置：[page_index.py:13](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L13)

用途：检查某个 section title 是否出现在目标页。

动态变量：

- `{title}`
- `{page_text}`

```text
Your job is to check if the given section appears or starts in the given page_text.

Note: do fuzzy matching, ignore any space inconsistency in the page_text.

The given section title is {title}.
The given page_text is {page_text}.

Reply format:
{

    "thinking": <why do you think the section appears or starts in the page_text>
    "answer": "yes or no" (yes if the section appears or starts in the page_text, no otherwise)
}
Directly return the final JSON structure. Do not output anything else.
```

### 2. `check_title_appearance_in_start`

位置：[page_index.py:48](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L48)

用途：检查 section 是否从当前页开头开始。

动态变量：

- `{title}`
- `{page_text}`

```text
You will be given the current section title and the current page_text.
Your job is to check if the current section starts in the beginning of the given page_text.
If there are other contents before the current section title, then the current section does not start in the beginning of the given page_text.
If the current section title is the first content in the given page_text, then the current section starts in the beginning of the given page_text.

Note: do fuzzy matching, ignore any space inconsistency in the page_text.

The given section title is {title}.
The given page_text is {page_text}.

reply format:
{
    "thinking": <why do you think the section appears or starts in the page_text>
    "start_begin": "yes or no" (yes if the section starts in the beginning of the page_text, no otherwise)
}
Directly return the final JSON structure. Do not output anything else.
```

### 3. `toc_detector_single_page`

位置：[page_index.py:104](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L104)

用途：判断单页是否为目录页。

动态变量：

- `{content}`

```text
Your job is to detect if there is a table of content provided in the given text.

Given text: {content}

return the following JSON format:
{
    "thinking": <why do you think there is a table of content in the given text>
    "toc_detected": "<yes or no>",
}

Directly return the final JSON structure. Do not output anything else.
Please note: abstract,summary, notation list, figure list, table list, etc. are not table of contents.
```

### 4. `check_if_toc_extraction_is_complete`

位置：[page_index.py:125](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L125)

用途：检查抽出的目录是否覆盖 partial document 的主要章节。

动态变量：

- `{content}` 通过字符串拼接注入
- `{toc}` 通过字符串拼接注入

```text
You are given a partial document  and a  table of contents.
Your job is to check if the  table of contents is complete, which it contains all the main sections in the partial document.

Reply format:
{
    "thinking": <why do you think the table of contents is complete or not>
    "completed": "yes" or "no"
}
Directly return the final JSON structure. Do not output anything else.

Document:
{content}
Table of contents:
{toc}
```

### 5. `check_if_toc_transformation_is_complete`

位置：[page_index.py:143](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L143)

用途：检查原始 TOC 到清洗后 TOC 的转换结果是否完整。

动态变量：

- `{content}` 通过字符串拼接注入
- `{toc}` 通过字符串拼接注入

```text
You are given a raw table of contents and a  table of contents.
Your job is to check if the  table of contents is complete.

Reply format:
{
    "thinking": <why do you think the cleaned table of contents is complete or not>
    "completed": "yes" or "no"
}
Directly return the final JSON structure. Do not output anything else.

Raw Table of contents:
{content}
Cleaned Table of contents:
{toc}
```

### 6. `extract_toc_content` 初始 prompt

位置：[page_index.py:160](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L160)

用途：从文本里抽完整目录内容。

动态变量：

- `{content}`

```text
Your job is to extract the full table of contents from the given text, replace ... with :

Given text: {content}

Directly return the full table of contents content. Do not output anything else.
```

### 7. `extract_toc_content` 续写 prompt

位置：[page_index.py:178](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L178)

用途：当目录抽取被截断时继续生成剩余部分。

```text
please continue the generation of table of contents , directly output the remaining part of the structure
```

### 8. `detect_page_index`

位置：[page_index.py:199](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L199)

用途：判断目录中是否包含页码。

动态变量：

- `{toc_content}`

```text
You will be given a table of contents.

Your job is to detect if there are page numbers/indices given within the table of contents.

Given text: {toc_content}

Reply format:
{
    "thinking": <why do you think there are page numbers/indices given within the table of contents>
    "page_index_given_in_toc": "<yes or no>"
}
Directly return the final JSON structure. Do not output anything else.
```

### 9. `toc_index_extractor`

位置：[page_index.py:240](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L240)

用途：给 TOC JSON 补 `physical_index`。

动态变量：

- `{toc}` 通过字符串拼接注入
- `{content}` 通过字符串拼接注入

```text
You are given a table of contents in a json format and several pages of a document, your job is to add the physical_index to the table of contents in the json format.

The provided pages contains tags like <physical_index_X> and <physical_index_X> to indicate the physical location of the page X.

The structure variable is the numeric system which represents the index of the hierarchy section in the table of contents. For example, the first section has structure index 1, the first subsection has structure index 1.1, the second subsection has structure index 1.2, etc.

The response should be in the following JSON format:
[
    {
        "structure": <structure index, "x.x.x" or None> (string),
        "title": <title of the section>,
        "physical_index": "<physical_index_X>" (keep the format)
    },
    ...
]

Only add the physical_index to the sections that are in the provided pages.
If the section is not in the provided pages, do not add the physical_index to it.
Directly return the final JSON structure. Do not output anything else.

Table of contents:
{toc}
Document pages:
{content}
```

### 10. `toc_transformer` 初始 prompt

位置：[page_index.py:270](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L270)

用途：把原始目录文本转为 `table_of_contents` JSON。

动态变量：

- `{toc_content}` 通过字符串拼接注入

```text
You are given a table of contents, You job is to transform the whole table of content into a JSON format included table_of_contents.

structure is the numeric system which represents the index of the hierarchy section in the table of contents. For example, the first section has structure index 1, the first subsection has structure index 1.1, the second subsection has structure index 1.2, etc.

The response should be in the following JSON format:
{
table_of_contents: [
    {
        "structure": <structure index, "x.x.x" or None> (string),
        "title": <title of the section>,
        "page": <page number or None>,
    },
    ...
    ],
}
You should transform the full table of contents in one go.
Directly return the final JSON structure, do not output anything else.

Given table of contents
:{toc_content}
```

### 11. `toc_transformer` 续写 prompt

位置：[page_index.py:304](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L304)

用途：继续补完未完成的 TOC JSON。

动态变量：

- `{toc_content}`
- `{last_complete}`

```text
Your task is to continue the table of contents json structure, directly output the remaining part of the json structure.
The response should be in the following JSON format:

The raw table of contents json structure is:
{toc_content}

The incomplete transformed table of contents json structure is:
{last_complete}

Please continue the json structure, directly output the remaining part of the json structure.
```

### 12. `add_page_number_to_toc`

位置：[page_index.py:453](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L453)

用途：在 partial document 中判断每个标题是否开始，并填充 `physical_index`。

动态变量：

- `{part}`
- `{json.dumps(structure, indent=2)}`

```text
You are given an JSON structure of a document and a partial part of the document. Your task is to check if the title that is described in the structure is started in the partial given document.

The provided text contains tags like <physical_index_X> and <physical_index_X> to indicate the physical location of the page X.

If the full target section starts in the partial given document, insert the given JSON structure with the "start": "yes", and "start_index": "<physical_index_X>".

If the full target section does not start in the partial given document, insert "start": "no",  "start_index": None.

The response should be in the following format.
    [
        {
            "structure": <structure index, "x.x.x" or None> (string),
            "title": <title of the section>,
            "start": "<yes or no>",
            "physical_index": "<physical_index_X> (keep the format)" or None
        },
        ...
    ]
The given structure contains the result of the previous part, you need to fill the result of the current part, do not change the previous result.
Directly return the final JSON structure. Do not output anything else.

Current Partial Document:
{part}

Given Structure
{json.dumps(structure, indent=2)}
```

### 13. `generate_toc_continue`

位置：[page_index.py:499](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L499)

用途：基于上一段已生成结构，继续生成当前段的扁平树结构。

动态变量：

- `{part}` 通过字符串拼接注入
- `{json.dumps(toc_content, indent=2)}` 通过字符串拼接注入

```text
You are an expert in extracting hierarchical tree structure.
You are given a tree structure of the previous part and the text of the current part.
Your task is to continue the tree structure from the previous part to include the current part.

The structure variable is the numeric system which represents the index of the hierarchy section in the table of contents. For example, the first section has structure index 1, the first subsection has structure index 1.1, the second subsection has structure index 1.2, etc.

For the title, you need to extract the original title from the text, only fix the space inconsistency.

The provided text contains tags like <physical_index_X> and <physical_index_X> to indicate the start and end of page X.

For the physical_index, you need to extract the physical index of the start of the section from the text. Keep the <physical_index_X> format.

The response should be in the following format.
    [
        {
            "structure": <structure index, "x.x.x"> (string),
            "title": <title of the section, keep the original title>,
            "physical_index": "<physical_index_X> (keep the format)"
        },
        ...
    ]

Directly return the additional part of the final JSON structure. Do not output anything else.

Given text
:{part}
Previous tree structure
:{json.dumps(toc_content, indent=2)}
```

### 14. `generate_toc_init`

位置：[page_index.py:534](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L534)

用途：直接从正文片段生成初始扁平树结构。

动态变量：

- `{part}` 通过字符串拼接注入

```text
You are an expert in extracting hierarchical tree structure, your task is to generate the tree structure of the document.

The structure variable is the numeric system which represents the index of the hierarchy section in the table of contents. For example, the first section has structure index 1, the first subsection has structure index 1.1, the second subsection has structure index 1.2, etc.

For the title, you need to extract the original title from the text, only fix the space inconsistency.

The provided text contains tags like <physical_index_X> and <physical_index_X> to indicate the start and end of page X.

For the physical_index, you need to extract the physical index of the start of the section from the text. Keep the <physical_index_X> format.

The response should be in the following format.
    [
        {
            "structure": <structure index, "x.x.x"> (string),
            "title": <title of the section, keep the original title>,
            "physical_index": "<physical_index_X> (keep the format)"
        },

    ],


Directly return the final JSON structure. Do not output anything else.

Given text
:{part}
```

### 15. `single_toc_item_index_fixer`

位置：[page_index.py:732](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/page_index.py#L732)

用途：对单个 section 重新定位其起始页。

动态变量：

- `{section_title}` 通过字符串拼接注入
- `{content}` 通过字符串拼接注入

```text
You are given a section title and several pages of a document, your job is to find the physical index of the start page of the section in the partial document.

The provided pages contains tags like <physical_index_X> and <physical_index_X> to indicate the physical location of the page X.

Reply in a JSON format:
{
    "thinking": <explain which page, started and closed by <physical_index_X>, contains the start of this section>,
    "physical_index": "<physical_index_X>" (keep the format)
}
Directly return the final JSON structure. Do not output anything else.

Section Title:
{section_title}
Document pages:
{content}
```

---

## `utils.py`

### 16. `generate_node_summary`

位置：[utils.py:618](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/utils.py#L618)

用途：给节点文本生成摘要。

动态变量：

- `{node['text']}`

```text
You are given a part of a document, your task is to generate a description of the partial document about what are main points covered in the partial document.

Partial Document Text: {node['text']}

Directly return the description, do not include any other text.
```

### 17. `generate_doc_description`

位置：[utils.py:662](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/utils.py#L662)

用途：基于整棵文档结构生成一句话描述。

动态变量：

- `{structure}`

```text
Your are an expert in generating descriptions for a document.
You are given a structure of a document. Your task is to generate a one-sentence description for the document, which makes it easy to distinguish the document from other documents.

Document Structure: {structure}

Directly return the description, do not include any other text.
```

---

## 备注

几个实现层面的事实：

- `page_index_md.py` 没有独立 prompt，它复用了 `utils.py` 里的摘要 prompt。
- 没有单独的 system prompt。
- 默认温度在 [llm.py:67](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/llm.py#L67)、[llm.py:80](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/llm.py#L80)、[llm.py:96](/Users/huangzhenxi/GitLab/OmniX/PageIndex/pageindex/llm.py#L96) 都是 `0`。
- `extract_toc_content` 和 `toc_transformer` 有续写逻辑，属于多轮 user/assistant 历史继续生成，不是单轮固定 prompt。
