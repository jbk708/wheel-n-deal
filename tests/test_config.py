from pathlib import Path

import pytest
from pydantic import ValidationError

from wheel_n_deal.config import Secrets, load_config

ROOT = Path(__file__).parent.parent


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


def _example() -> str:
    return (ROOT / "config.example.yaml").read_text()


def test_example_config_loads():
    config = load_config(ROOT / "config.example.yaml")
    assert config.ntfy.topic == "deals"
    assert config.llm.model == "mimo-v2.6-flash"
    assert config.data_dir == Path("/data")
    assert config.heartbeat_url is None
    assert config.politeness.min_interval_hours >= 1
    assert config.watch
    first = config.watch[0]
    assert first.url.startswith("https://")
    assert first.target_price > 0


def test_notes_optional_and_loaded(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    assert any(item.notes is None for item in config.watch)
    assert any(item.notes for item in config.watch)


def test_watch_is_optional(tmp_path):
    text = """
ntfy: {url: https://ntfy.example}
llm: {base_url: https://llm.example/v1}
"""
    assert load_config(_write(tmp_path, text)).watch == []


def test_unknown_key_rejected(tmp_path):
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, _example() + "\nbogus: 1\n"))


def test_secret_in_yaml_rejected(tmp_path):
    text = _example().replace("ntfy:\n", "ntfy:\n  token: abc\n")
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, text))


def test_non_positive_target_rejected(tmp_path):
    text = """
ntfy: {url: https://ntfy.example}
llm: {base_url: https://llm.example/v1}
watch:
  - {url: https://shop.example/p/1, name: Thing, target_price: 0}
"""
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, text))


def test_non_http_url_rejected(tmp_path):
    text = """
ntfy: {url: https://ntfy.example}
llm: {base_url: https://llm.example/v1}
watch:
  - {url: "file:///etc/passwd", name: Thing, target_price: 5}
"""
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, text))


def test_duplicate_urls_rejected(tmp_path):
    text = """
ntfy: {url: https://ntfy.example}
llm: {base_url: https://llm.example/v1}
watch:
  - {url: https://shop.example/p/1, name: A, target_price: 5}
  - {url: https://shop.example/p/1, name: B, target_price: 6}
"""
    with pytest.raises(ValidationError, match="duplicate"):
        load_config(_write(tmp_path, text))


def test_minimal_config_defaults(tmp_path):
    text = """
ntfy: {url: https://ntfy.example}
llm: {base_url: https://llm.example/v1}
watch:
  - {url: https://shop.example/p/1, name: Thing, target_price: 19.99}
heartbeat_url: https://kuma.example/api/push/x
"""
    config = load_config(_write(tmp_path, text))
    assert config.ntfy.topic == "deals"
    assert config.llm.model == "mimo-v2.6-flash"
    assert config.politeness.min_interval_hours == 6
    assert config.politeness.jitter_minutes == 30
    assert config.heartbeat_url == "https://kuma.example/api/push/x"


def test_secrets_from_env():
    secrets = Secrets.from_env({"LLM_API_KEY": "k", "NTFY_TOKEN": "t", "WND_API_TOKEN": "a"})
    assert secrets.llm_api_key == "k"
    assert secrets.ntfy_token == "t"
    assert secrets.api_token == "a"


def test_secrets_missing_or_empty_are_none():
    secrets = Secrets.from_env({"NTFY_TOKEN": ""})
    assert secrets.llm_api_key is None
    assert secrets.ntfy_token is None
    assert secrets.api_token is None


def test_secrets_repr_hides_values():
    secrets = Secrets.from_env(
        {"LLM_API_KEY": "sekrit", "NTFY_TOKEN": "tok", "WND_API_TOKEN": "apitok"}
    )
    assert "sekrit" not in repr(secrets)
    assert "tok" not in repr(secrets)
    assert "apitok" not in repr(secrets)
