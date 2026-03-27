from pageindex.core.utils import token_counter


def test_count_tokens_falls_back_when_model_encoding_is_unavailable(monkeypatch):
    class _Encoding:
        def encode(self, text):
            return text.split()

    monkeypatch.setattr(token_counter.tiktoken, "encoding_for_model", lambda model: (_ for _ in ()).throw(KeyError(model)))
    monkeypatch.setattr(token_counter.tiktoken, "get_encoding", lambda name: _Encoding())

    assert token_counter.count_tokens("alpha beta gamma", model="unknown-model") == 3


def test_count_tokens_uses_character_estimate_when_all_tokenizers_fail(monkeypatch):
    monkeypatch.setattr(token_counter.tiktoken, "encoding_for_model", lambda model: (_ for _ in ()).throw(KeyError(model)))
    monkeypatch.setattr(token_counter.tiktoken, "get_encoding", lambda name: (_ for _ in ()).throw(ValueError(name)))

    assert token_counter.count_tokens("abcdefghij", model="unknown-model") == 2


def test_count_tokens_uses_qwen_transformers_tokenizer(monkeypatch):
    class _Tokenizer:
        def encode(self, text):
            return list(text)

    class _AutoTokenizer:
        @staticmethod
        def from_pretrained(model_name, trust_remote_code):
            assert model_name == "Qwen/Qwen3-30B-A3B-Instruct-2507"
            assert trust_remote_code is True
            return _Tokenizer()

    token_counter._build_transformers_encoder.cache_clear()
    monkeypatch.setattr(token_counter, "AutoTokenizer", _AutoTokenizer)

    assert token_counter.count_tokens("你好，世界", model="Qwen3-30B-A3B-Instruct-2507") == 5


def test_count_tokens_falls_back_from_qwen_to_tiktoken(monkeypatch):
    class _Encoding:
        def encode(self, text):
            return text.split()

    token_counter._build_transformers_encoder.cache_clear()
    monkeypatch.setattr(token_counter, "AutoTokenizer", None)
    monkeypatch.setattr(token_counter.tiktoken, "encoding_for_model", lambda model: (_ for _ in ()).throw(KeyError(model)))
    monkeypatch.setattr(token_counter.tiktoken, "get_encoding", lambda name: _Encoding())

    assert token_counter.count_tokens("alpha beta gamma", model="Qwen/Qwen3-30B-A3B-Instruct-2507") == 3
