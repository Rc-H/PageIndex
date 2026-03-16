from functools import lru_cache

import tiktoken

try:
    from transformers import AutoTokenizer
except ImportError:
    AutoTokenizer = None


DEFAULT_OPENAI_MODEL = "gpt-4o"
QWEN_HUB_PREFIX = "Qwen/"


def count_tokens(text, model=None):
    if not text:
        return 0
    return len(get_token_encoder(model)(text))


def get_token_encoder(model=None):
    normalized_model = _normalize_model_name(model)

    if _is_qwen_model(normalized_model):
        try:
            return _build_transformers_encoder(_resolve_transformers_model_name(normalized_model))
        except Exception:
            pass

    try:
        enc = tiktoken.encoding_for_model(normalized_model)
        return enc.encode
    except Exception:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return enc.encode
        except Exception:
            return _estimate_tokens


def _normalize_model_name(model):
    normalized = (model or DEFAULT_OPENAI_MODEL).strip()
    return normalized or DEFAULT_OPENAI_MODEL


def _is_qwen_model(model):
    normalized = model.lower()
    return normalized.startswith("qwen") or "/qwen" in normalized


def _resolve_transformers_model_name(model):
    if "/" in model:
        return model
    if model.lower().startswith("qwen"):
        return f"{QWEN_HUB_PREFIX}{model}"
    return model


@lru_cache(maxsize=8)
def _build_transformers_encoder(model_name):
    if AutoTokenizer is None:
        raise ImportError("transformers is required for non-tiktoken tokenizers")

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    return tokenizer.encode


def _estimate_tokens(text):
    return [None] * max(1, len(text or "") // 4)
