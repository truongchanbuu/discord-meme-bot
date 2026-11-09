"""YAML options and environment-backed credentials are validated before startup."""

from pathlib import Path
from shutil import copytree
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from meme_manager.config import RuntimeConfig, Settings


def test_loads_without_channel_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "1")
    with patch("meme_manager.config.load_dotenv"):
        settings = Settings.from_environment()
    assert settings.guild_id == 1


@pytest.mark.parametrize("value", ["", "0", "-1", "not-an-id"])
def test_requires_positive_guild_id(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", value)
    with (
        patch("meme_manager.config.load_dotenv"),
        pytest.raises(ValueError, match="DISCORD_GUILD_ID"),
    ):
        Settings.from_environment()


@pytest.fixture
def config_directory(tmp_path: Path) -> Path:
    target = tmp_path / "config"
    copytree(Path("config"), target)
    return target


@pytest.mark.parametrize(
    ("name", "key", "value"),
    [
        ("bot", "page_size", 26),
        ("bot", "page_size", True),
        ("bot", "log_level", "silent"),
        ("bot", "history_default", 1001),
        ("bot", "token_env", "../secret"),
        ("bot", "category_name", "x" * 101),
        ("database", "timeout_seconds", -1),
        ("search", "min_fuzzy_score", 101),
        ("search", "min_fuzzy_score", float("nan")),
        ("search", "max_results", "100"),
        ("search", "unknown_option", 10),
    ],
)
def test_runtime_rejects_invalid_options(
    config_directory: Path, name: str, key: str, value: Any
) -> None:
    source = config_directory / f"{name}.yaml"
    values = yaml.safe_load(source.read_text())
    values[key] = value
    source.write_text(yaml.safe_dump(values))
    with pytest.raises(ValueError):
        RuntimeConfig.load(config_directory)


@pytest.mark.parametrize(
    "group",
    [
        {"kind": "audio", "enabled": True, "extensions": ["mp3"]},
        {"kind": "image", "enabled": "yes", "extensions": ["bmp"]},
        {"kind": "image", "enabled": True, "extensions": [".bmp"]},
        {"kind": "image", "enabled": True, "extensions": ["png"]},
        {"kind": "image", "enabled": True, "extensions": []},
    ],
)
def test_runtime_rejects_invalid_media_group(config_directory: Path, group: dict[str, Any]) -> None:
    source = config_directory / "media.yaml"
    values = yaml.safe_load(source.read_text())
    values["types"]["extra"] = group
    source.write_text(yaml.safe_dump(values))
    with pytest.raises(ValueError):
        RuntimeConfig.load(config_directory)


def test_environment_directory_and_custom_environment_names(
    config_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = config_directory / "bot.yaml"
    values = yaml.safe_load(source.read_text())
    values.update(token_env="CUSTOM_TOKEN", guild_id_env="CUSTOM_GUILD", category_name="Thư viện")
    source.write_text(yaml.safe_dump(values))
    monkeypatch.setenv("MEME_CONFIG_DIR", str(config_directory))
    monkeypatch.setenv("CUSTOM_TOKEN", "test-token")
    monkeypatch.setenv("CUSTOM_GUILD", "42")
    monkeypatch.setenv("MEME_DB_PATH", "data/local.sqlite3")
    with patch("meme_manager.config.load_dotenv"):
        settings = Settings.from_environment()
    assert settings.guild_id == 42
    assert settings.database_path.as_posix() == "data/local.sqlite3"
    assert settings.config.bot.category_name == "Thư viện"
