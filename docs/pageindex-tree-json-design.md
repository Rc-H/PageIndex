# PageIndex 文件转 Tree JSON 设计说明

这份说明聚焦一个问题：`PageIndex` 现在是怎么把一个文件变成最终的 `Tree JSON` 的。

核心结论先放前面：

1. `PageIndex` 不是只有一条“文件 -> Tree”流水线，而是按文件类型分成三条路径：
   - PDF：基于页文本、目录识别、页码对齐、再转树。
   - Markdown：基于 `#` 标题层级直接建树。
   - DOCX / DOC：基于 Word 标题样式直接建树，`.doc` 先转 `.docx`。
2. PDF 路径的核心中间态是“扁平 TOC 列表 + physical_index”，然后再变成带 `start_index/end_index` 的树。
3. Markdown / DOCX 路径的核心中间态是“扁平 heading 列表 + level”，然后用栈直接建树。
4. 因此，虽然最终都叫 `structure`，但不同文件类型输出的字段并不完全一致。

---

## 1. 入口在哪里

统一入口在 `pageindex/document_indexers.py` 的 `DocumentIndexer.index()`。

- `infer_file_type()` 根据后缀判断类型。
- `_index_pdf()` 调 `page_index_main()`。
- `_index_markdown()` 调 `md_to_tree()`。
- `_index_docx()` 自己提取 heading，再复用 markdown 那套 `build_tree_from_nodes()`。
- `_index_doc()` 先用 LibreOffice 转成 `.docx`，再走 `_index_docx()`。

可以把它理解成：

```text
file
  -> DocumentIndexer.index()
     -> pdf      -> PDF tree builder
     -> md       -> Markdown tree builder
     -> docx/doc -> Word tree builder
```

---

## 2. 最终 Tree JSON 长什么样

### PDF 路径的典型结构

PDF 最终更偏“页级索引树”：

```json
{
  "title": "Section Title",
  "start_index": 12,
  "end_index": 18,
  "node_id": "0007",
  "summary": "...",
  "nodes": []
}
```

这里最关键的是：

- `start_index` / `end_index`：节点覆盖的物理页范围。
- `nodes`：子节点。
- `summary`：基于这个节点覆盖页文本生成的摘要。

### Markdown / DOCX 路径的典型结构

这两条路径更偏“文档结构树”：

```json
{
  "title": "Section Title",
  "node_id": "0007",
  "line_num": 42,
  "summary": "...",
  "prefix_summary": "...",
  "nodes": []
}
```

这里最关键的是：

- `line_num`：标题在原文中的起始行。
- 没有 `start_index` / `end_index`，因为它们不是按 PDF 页来切的。
- 叶子节点更常见 `summary`，非叶子节点更常见 `prefix_summary`。

这点很重要：`PageIndex` 目前并没有为所有文件类型强行统一成一个完全相同的 schema。

---

## 3. PDF 怎么变成 Tree JSON

PDF 路径在 `pageindex/page_index.py`，真正的总入口是 `page_index_main()`。

### 3.1 第一步：先把 PDF 变成页列表

`page_index_main()` 先调用 `get_page_tokens()`：

- 读出每一页的文本。
- 顺便计算每一页 token 数。
- 得到 `page_list = [(page_text, token_length), ...]`。

这一步之后，整个系统处理的基本单位就不是“文件”，而是“页面列表”。

---

### 3.2 第二步：判断能不能利用目录

`tree_parser()` 会先调 `check_toc()`。

`check_toc()` 做三件事：

1. `find_toc_pages()`：找哪些页看起来像目录页。
2. `toc_extractor()`：把这些目录页拼成目录文本。
3. `detect_page_index()`：判断目录里有没有印刷页码。

然后系统根据结果决定后续策略。

---

### 3.3 第三步：先构造“扁平目录列表”

PDF 路径不是直接生成树，而是先生成一个扁平列表，列表元素大致长这样：

```json
{
  "structure": "2.3",
  "title": "Risk Factors",
  "physical_index": 17
}
```

这里：

- `structure` 是逻辑层级编码，比如 `1`、`1.2`、`1.2.3`。
- `physical_index` 是 PDF 物理页。

这个“扁平列表”是 PDF 路径里最关键的中间态。

#### 情况 A：目录里带页码

走 `process_toc_with_page_numbers()`：

1. `toc_transformer()` 先把原始目录文本转成 JSON：
   - `structure`
   - `title`
   - `page`
2. `toc_index_extractor()` 再去正文前几页里找这些标题真实出现在哪个物理页，拿到一部分 `physical_index`。
3. `extract_matching_page_pairs()` + `calculate_page_offset()` 计算“目录页码”和“PDF物理页码”的 offset。
4. `add_page_offset_to_toc_json()` 把目录里的 `page` 批量映射成 `physical_index`。
5. `process_none_page_numbers()` 补齐少数缺失的页。

也就是说，这条路本质上是：

```text
目录给 page
  + 正文抽样给 physical_index
  -> 算 offset
  -> 全量映射成 physical_index
```

#### 情况 B：没有可靠目录时

走 `process_no_toc()`：

1. 给每页文本打上 `<physical_index_X>` 标签。
2. 用 `page_list_to_group_text()` 按 token 切成多个 group。
3. 第一段用 `generate_toc_init()` 生成初始扁平结构。
4. 后续段用 `generate_toc_continue()` 续写结构。
5. 最后把 `physical_index` 从字符串标签转成整数。

这条路可以理解成“直接从正文生成目录骨架”。

---

### 3.4 第四步：校验和修正 `physical_index`

`meta_processor()` 是 PDF 扁平结构的总调度器。

它做的事情是：

1. 过滤掉没有 `physical_index` 的项。
2. `validate_and_truncate_physical_indices()`：把超出文档范围的页号砍掉。
3. `verify_toc()`：检查每个标题是否真的出现在它声明的页。
4. 如果准确率还可以但有少量错误，走 `fix_incorrect_toc_with_retries()` 修复。
5. 如果当前策略效果不好，就降级到更保守的策略。

这一步说明一个设计思路：PageIndex 不完全相信第一次 LLM 产出的 TOC，而是会做二次验证。

---

### 3.5 第五步：从扁平列表变成真正的树

到这一步，数据还只是：

```json
[
  { "structure": "1", "title": "...", "physical_index": 1 },
  { "structure": "1.1", "title": "...", "physical_index": 3 },
  { "structure": "2", "title": "...", "physical_index": 9 }
]
```

`tree_parser()` 接下来做两件关键事：

#### 先算页范围

`check_title_appearance_in_start_concurrent()` 会判断“下一个标题是不是从它所在页开头开始”。

然后 `post_processing()` 把每个节点的：

- `physical_index` -> `start_index`
- 下一项的 `physical_index` -> 当前项的 `end_index`

规则大致是：

- 如果下一个 section 从下一页开头开始，则当前节点 `end_index = next_start - 1`
- 否则当前节点 `end_index = next_start`
- 最后一个节点的 `end_index = 文档最后一页`

所以，PDF 树里的页范围不是 LLM 直接一次性给出的，而是“先定位起点，再根据相邻节点推导终点”。

#### 再按 `structure` 编码建树

`post_processing()` 里最终会调 `list_to_tree()`：

- `1` 是根节点
- `1.2` 挂到 `1` 下面
- `1.2.3` 挂到 `1.2` 下面

因此，PDF 的树结构本质上是由 `structure` 字段决定的，不是由页码决定的。

页码负责“范围”，`structure` 负责“父子关系”。

---

### 3.6 第六步：对大节点递归细分

`process_large_node_recursively()` 会检查一个节点是否过大：

- 页数超过 `max_page_num_each_node`
- token 也超过 `max_token_num_each_node`

如果过大，就只拿这个节点覆盖的页，再跑一遍 `meta_processor()`，给它补更细的子树。

这一步是当前 PDF 设计里很关键的层次化策略：

- 第一次先得到粗树。
- 只对大块再继续向下细分。

所以它不是一次性把整本 PDF 拉到最细层级，而是递归下钻。

---

### 3.7 第七步：补充 node_id、text、summary、doc_description

`page_index_main()` 在树结构稳定后再决定是否补充：

- `write_node_id()`：补 `node_id`
- `add_node_text()`：把 `start_index~end_index` 的页文本挂回节点
- `generate_summaries_for_structure()`：给节点生成 `summary`
- `generate_doc_description()`：给整个文档生成一句话描述

注意这里的顺序是有意的：

- 先确定树和页范围
- 再回填文本
- 最后再做摘要

这样摘要才能基于最终节点范围来做。

---

## 4. Markdown 怎么变成 Tree JSON

Markdown 路径在 `pageindex/page_index_md.py`，逻辑比 PDF 直很多。

### 4.1 提取标题节点

`extract_nodes_from_markdown()`：

- 扫描所有行。
- 识别 `#` 到 `######` 标题。
- 跳过代码块里的标题样式文本。
- 产出扁平节点：`node_title + line_num`。

### 4.2 给每个标题切正文

`extract_node_text_content()`：

- 根据当前标题行到下一个标题行之间的内容，切出当前节点的 `text`。
- 同时根据 `#` 的数量得出 `level`。

所以 markdown 的中间态是：

```json
{
  "title": "Section",
  "line_num": 12,
  "level": 2,
  "text": "## Section\n..."
}
```

### 4.3 可选的 thinning

如果 `if_thinning=yes`：

1. `update_node_list_with_text_token_count()` 先计算每个节点连同全部子节点的 token 数。
2. `tree_thinning_for_index()` 会把过小的父节点和后代内容合并，减少碎节点。

这个设计是在 markdown 上做“结构压缩”，避免树太碎。

### 4.4 用 level 直接建树

`build_tree_from_nodes()` 用一个栈处理层级：

- 当前节点 level 比栈顶小或相等，就弹栈。
- 栈空则作为根节点。
- 否则挂到最近的更高层父节点下面。

这一步的父子关系完全由 `level` 决定。

和 PDF 的差别很明显：

- PDF：靠 `structure = 1.2.3`
- Markdown：靠 `level = 1/2/3`

### 4.5 生成摘要和描述

`generate_summaries_for_structure_md()` 的策略是：

- 叶子节点写 `summary`
- 非叶子节点写 `prefix_summary`

如果节点文本很短，小于 `summary_token_threshold`，就直接把原文当摘要，不再额外调模型。

最后 `md_to_tree()` 返回：

```json
{
  "doc_name": "...",
  "structure": [...]
}
```

如果开启文档描述，还会再带一个 `doc_description`。

---

## 5. DOCX / DOC 怎么变成 Tree JSON

DOCX 路径在 `pageindex/document_indexers.py`。

它本质上是在 Word 文档上复用 markdown 那套“heading -> flat nodes -> tree”的思想。

### 5.1 先把 Word 文档转成块流

`_iter_docx_blocks()` 按文档顺序遍历：

- 段落 `p`
- 表格 `tbl`

如果段落样式是 `Heading 1/2/3...`，就视为结构节点；否则视为正文文本。

### 5.2 组装成扁平节点

`_extract_docx_nodes()` 维护一个 `current_node + body_buffer`：

- 遇到 heading，结束上一个节点，开启新节点。
- 遇到普通段落或表格，把文本追加到当前节点正文。
- 如果文档开头就没有 heading，会自动创建一个 `fallback_title` 作为根节点。

中间态大概是：

```json
{
  "title": "Executive Summary",
  "line_num": 1,
  "level": 1,
  "text": "Executive Summary\nRevenue increased ..."
}
```

### 5.3 后续直接复用 markdown 的建树和摘要能力

DOCX 后面直接调用：

- `build_tree_from_nodes()`
- `write_node_id()`
- `generate_summaries_for_structure_md()`
- `format_structure()`
- `generate_doc_description()`

所以 DOCX 路径和 Markdown 路径在“树构建思想”上几乎是同一套。

### 5.4 DOC 的处理

`.doc` 没有单独建树逻辑。

`_index_doc()` 只是：

1. 调 LibreOffice 转 `.docx`
2. 再调用 `_index_docx()`

---

## 6. 当前设计里最值得注意的几个点

### 6.1 PDF 和非 PDF 的 schema 实际上不统一

PDF 侧重点是：

- `start_index`
- `end_index`
- 页范围上的定位和检索

Markdown / DOCX 侧重点是：

- `line_num`
- heading 层级
- 文档内结构表达

所以现在的 `Tree JSON` 更准确地说是“同一风格，但不是完全同构”。

---

### 6.2 PDF 的核心不是“直接生成树”，而是“先生成扁平结构，再建树”

这点是最容易看漏的。

PDF 路径真正的关键对象不是最终树，而是这个扁平列表：

```json
{ "structure": "1.2", "title": "...", "physical_index": 8 }
```

后面的大部分逻辑，其实都在做三件事：

1. 让 `physical_index` 尽量可靠。
2. 用相邻节点推导 `start_index/end_index`。
3. 用 `structure` 组装出父子关系。

---

### 6.3 目前“TOC 但不带页码”的分支不是主入口

代码里有 `process_toc_no_page_numbers()`，但当前 `tree_parser()` 的主判断是：

- 目录存在且带页码：走 `process_toc_with_page_numbers`
- 否则：直接走 `process_no_toc`

也就是说，目录存在但没有页码时，当前主流程并不会优先用这份 TOC 作为骨架，而是更像“直接从正文重建结构”。

这不是 bug 说明，而是一个当前实现上的真实设计特征。读代码时如果觉得 `process_toc_no_page_numbers()` 好像存在感很弱，这就是原因。

---

### 6.4 Markdown / DOCX 的建树是确定性的，PDF 的建树是“LLM + 规则”的混合式

Markdown / DOCX：

- 规则比较硬。
- 层级主要靠标题 level。
- 更像 parser。

PDF：

- 先靠 LLM 抽目录 / 对齐页码 / 验证标题页。
- 再靠规则推页范围和树关系。
- 更像“结构抽取器 + 后处理器”。

---

### 6.5 `node_id` 是后补的，不是树构建的本体

不管是 PDF 还是 DOCX / Markdown，`node_id` 都更像结果增强字段，不参与树关系推导。

- PDF 里树关系由 `structure` 决定。
- Markdown / DOCX 里树关系由 `level` 决定。

所以如果以后要重构，这个字段可以继续保留，但不该成为核心依赖。

---

## 7. 我对当前设计的理解总结

如果只用一句话概括：

**PageIndex 当前的“文件转 Tree JSON”设计，本质是按文件类型分成两种范式：PDF 走“目录/页码定位范式”，Markdown 和 DOCX 走“标题层级解析范式”。**

再展开一点：

- PDF 强在“可定位到页”，适合检索和引用。
- Markdown / DOCX 强在“结构稳定、实现直接”，但没有 PDF 那种页范围定位。
- 最终都输出 `structure`，但不同来源文件的结构信息密度不一样。

如果你后面要继续改这块，我建议优先把下面三个概念在代码里明确分层：

1. `Flat structural hints`
   - PDF: `structure + physical_index`
   - MD/DOCX: `level + line_num`
2. `Canonical tree node`
   - 统一定义最小公共字段
3. `Enrichment`
   - `node_id`
   - `text`
   - `summary`
   - `doc_description`

这样后续无论是统一 schema，还是增加 HTML / Notion / OCR 文档入口，都会更容易。

---

## 8. 对照源码时建议优先读的顺序

如果你想最快看懂，建议按这个顺序读：

1. `pageindex/document_indexers.py`
2. `pageindex/page_index.py` 的 `page_index_main()`、`tree_parser()`、`meta_processor()`
3. `pageindex/utils.py` 的 `post_processing()`、`list_to_tree()`
4. `pageindex/page_index_md.py`

对应关系可以记成：

```text
入口分流
  -> PDF 扁平结构生成
  -> 扁平结构校验
  -> 扁平结构转树
  -> 文本/摘要增强
```

如果你需要，我下一步可以继续帮你把这份说明再压成一张“调用链图”，或者直接给你补一版“统一 schema / 重构建议” markdown。
