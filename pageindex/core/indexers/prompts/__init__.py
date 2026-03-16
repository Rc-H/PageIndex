from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_ROOT = Path(__file__).parents[1]


@lru_cache(maxsize=1)
def _prompt_index() -> dict[str, Path]:
    prompt_paths = {}

    for prompt_path in _PROMPTS_ROOT.rglob("prompts/*.txt"):
        name = prompt_path.name
        if name in prompt_paths:
            raise ValueError(
                f"Duplicate prompt name '{name}' found at "
                f"'{prompt_paths[name]}' and '{prompt_path}'"
            )
        prompt_paths[name] = prompt_path

    return prompt_paths


@lru_cache(maxsize=None)
def _read(name: str) -> str:
    try:
        prompt_path = _prompt_index()[name]
    except KeyError as exc:
        raise FileNotFoundError(f"Prompt '{name}' not found under '{_PROMPTS_ROOT}'") from exc
    return prompt_path.read_text(encoding="utf-8")


def load_prompt(name: str, **kwargs) -> str:
    template = _read(name)
    if kwargs:
        return template.format(**kwargs)
    return template
