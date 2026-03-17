from __future__ import annotations

from functools import lru_cache
from pathlib import Path


_INDEXERS_ROOT = Path(__file__).parent


@lru_cache(maxsize=1)
def _prompt_index() -> dict[str, Path]:
    prompt_paths: dict[str, Path] = {}

    for prompt_path in _INDEXERS_ROOT.rglob("prompts/*.txt"):
        relative_name = prompt_path.relative_to(_INDEXERS_ROOT).as_posix()
        prompt_paths[relative_name] = prompt_path

        basename = prompt_path.name
        if basename in prompt_paths and prompt_paths[basename] != prompt_path:
            continue
        prompt_paths.setdefault(basename, prompt_path)

    return prompt_paths


@lru_cache(maxsize=None)
def _read(name: str) -> str:
    try:
        prompt_path = _prompt_index()[name]
    except KeyError as exc:
        raise FileNotFoundError(f"Prompt '{name}' not found under '{_INDEXERS_ROOT}'") from exc
    return prompt_path.read_text(encoding="utf-8")


def load_prompt(name: str, **kwargs) -> str:
    template = _read(name)
    if kwargs:
        return template.format(**kwargs)
    return template
