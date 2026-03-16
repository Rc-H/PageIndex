# CLAUDE.md

This file guides coding agents working in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run service
python run_pageindex_service.py

# Run tests
pytest
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```

## Architecture

### Project Layout

```
pageindex/
├── api/            — FastAPI app and route definitions
├── core/
│   ├── indexers/   — Format-specific document indexers (PDF, Markdown, DOCX)
│   ├── services/   — Async task orchestration
│   └── utils/      — Utility functions (PDF, JSON, tree, tokens)
├── infrastructure/ — External adapters (LLM, settings)
└── messages/       — Request/response contracts (dataclasses)
```

### Layer Rules

- `api/` dispatches to `services/` only — no business logic in route handlers
- `services/` orchestrates `indexers/` and `infrastructure/` — no HTTP concerns
- `indexers/` are pure document processing — no I/O except file reads
- `infrastructure/` wraps all external services (LLM API, env config)
- `messages/` contains only frozen dataclasses — no logic

## Code Style

### Core Methods Must Be Abstract

The body of any "orchestration" method should read like a sequence of named steps, not implementation details. Extract all non-trivial logic into named sub-methods.

**Good:**
```python
async def index(self, file_path, model, options):
    pages = self._load_pages(file_path)
    structure = await self._extract_structure(pages, model)
    validated = await self._validate_titles(structure, pages)
    return self._build_result(validated)
```

**Bad:**
```python
async def index(self, file_path, model, options):
    reader = PdfReader(file_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append({"index": i + 1, "text": text.strip()})
    prompt = f"Extract the structure from these pages:\n{pages}"
    response = await llm.generate(model, prompt)
    ...  # 80 more lines
```

### File Length and Responsibility

- **Hard limit: ~300 lines per file.** If a file exceeds this, split it.
- One responsibility per file. When in doubt, create a new file.
- Prefer many small focused files over one large file.

### Splitting Guide by Module

| Current File | Split Into |
|---|---|
| `core/utils/utils.py` | `pdf_reader.py`, `json_utils.py`, `tree.py`, `token_counter.py` |
| `core/indexers/page_index.py` | `toc_extractor.py`, `title_validator.py`, `prompts.py`, `page_indexer.py` |
| `core/indexers/document_indexers.py` | `docx_parser.py` + keep `document_indexers.py` as thin dispatcher |

### Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Private methods: `_snake_case`
- Constants: `UPPER_SNAKE_CASE`

### Settings and Environment

All `os.getenv()` calls live exclusively in `infrastructure/settings.py`.
No other file may read environment variables directly.

```python
# Good — read from settings object
def __init__(self, settings: ServiceSettings): ...

# Bad — direct env access outside settings.py
api_key = os.getenv("OPENAI_API_KEY")
```

### LLM Prompts

Prompt strings must not be inlined inside business logic methods.
Define them as named constants or builder functions in a dedicated `prompts.py` file within the relevant module.

```python
# Good
from pageindex.core.indexers.prompts import build_structure_prompt

prompt = build_structure_prompt(pages, model)

# Bad
prompt = f"You are a document analyzer. Given these {len(pages)} pages..."
```

### Async

- Use `async/await` only where actual I/O is involved (LLM calls, HTTP, file reads).
- Do not make sync utility functions async.

## Testing

- Unit tests: pure logic, no I/O, no LLM calls — use fakes from `tests/helpers.py`
- Integration tests: real file parsing, no network
- E2E tests: full HTTP stack with `TestClient`, fake LLM and indexer

Test file mirrors source file structure:
```
pageindex/core/indexers/toc_extractor.py  →  tests/unit/test_toc_extractor.py
```
