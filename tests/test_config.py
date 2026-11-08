"""Only the token, guild ID and local database are configured by the operator."""

from unittest.mock import patch

import pytest

from meme_manager.config import Settings


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
