"""Named config reads use safe YAML and reject invalid paths and document shapes."""

from pathlib import Path

import pytest

from meme_manager.services.config import ConfigService


def test_loads_by_name_and_reads_updated_file(tmp_path: Path) -> None:
    source = tmp_path / "search.yaml"
    source.write_text("limit: 3\n", encoding="utf-8")
    service = ConfigService(tmp_path)
    assert service.load("search") == {"limit": 3}
    source.write_text("limit: 7\n", encoding="utf-8")
    assert service.load("search") == {"limit": 7}


@pytest.mark.parametrize("name", ["../secret", "/tmp/secret", "search.yaml", "a/b", "a\\b", ""])
def test_rejects_names_that_are_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="Config name"):
        ConfigService(tmp_path).load(name)


@pytest.mark.parametrize("document", ["", "- one", "true", "42", "1: value"])
def test_requires_a_string_key_mapping(tmp_path: Path, document: str) -> None:
    (tmp_path / "bot.yaml").write_text(document, encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        ConfigService(tmp_path).load("bot")


@pytest.mark.parametrize(
    "document", ["secret: [private-value", "!!python/object:builtins.object {}"]
)
def test_invalid_or_unsafe_yaml_has_sanitized_error(tmp_path: Path, document: str) -> None:
    (tmp_path / "bot.yaml").write_text(document, encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid YAML in config bot") as error:
        ConfigService(tmp_path).load("bot")
    assert "private-value" not in str(error.value)


def test_missing_file_is_not_silently_defaulted(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ConfigService(tmp_path).load("missing")
