"""CLI dry runs must never require a token or write the database or Discord."""

import asyncio
from pathlib import Path
from shutil import copytree
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from meme_manager.config import RuntimeConfig, Settings
from meme_manager.import_folder import main, upload_plan
from meme_manager.services.folder_import import FolderPlan, ImportSummary


def test_dry_run_does_not_load_credentials_connect_or_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "cat.gif").write_bytes(b"image")
    with (
        patch("meme_manager.import_folder.Settings.from_environment") as settings,
        patch("meme_manager.import_folder.discord.Client") as client,
        patch("meme_manager.import_folder.SQLiteDatabase") as database,
    ):
        assert main([str(tmp_path), "--dry-run", "--category", "Mèo Khóc"]) == 0
    settings.assert_not_called()
    client.assert_not_called()
    database.assert_not_called()
    assert "PLAN #meo-khoc: cat.gif" in capsys.readouterr().out


def test_empty_folder_exits_without_network(tmp_path: Path) -> None:
    with patch("meme_manager.import_folder.Settings.from_environment") as settings:
        assert main([str(tmp_path)]) == 0
    settings.assert_not_called()


def test_missing_folder_exits_nonzero(tmp_path: Path) -> None:
    assert main([str(tmp_path / "missing"), "--dry-run"]) == 2


def test_upload_client_logs_in_without_gateway(tmp_path: Path, config: RuntimeConfig) -> None:
    settings = Settings("test-token", 1, tmp_path / "catalog.sqlite3", config=config)
    client = AsyncMock()
    client.__aenter__.return_value = client
    with (
        patch("meme_manager.import_folder.discord.Client", return_value=client),
        patch("meme_manager.import_folder.CategoryManager"),
        patch("meme_manager.import_folder.DiscordFolderUploader"),
        patch("meme_manager.import_folder.FolderImportService") as service,
    ):
        service.return_value.run = AsyncMock(return_value=ImportSummary())
        assert asyncio.run(upload_plan(settings, FolderPlan())) == 0
    client.login.assert_awaited_once_with("test-token")
    client.fetch_guild.assert_awaited_once_with(1)
    client.connect.assert_not_awaited()
    client.start.assert_not_awaited()
    client.run.assert_not_called()


def test_dry_run_uses_media_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "config"
    copytree(Path("config"), directory)
    source = directory / "media.yaml"
    values = yaml.safe_load(source.read_text())
    values["types"]["gif"]["enabled"] = False
    source.write_text(yaml.safe_dump(values))
    monkeypatch.setenv("MEME_CONFIG_DIR", str(directory))
    media = tmp_path / "memes"
    media.mkdir()
    (media / "cat.gif").write_bytes(b"gif")
    (media / "cat.png").write_bytes(b"png")
    with patch("meme_manager.import_folder.discord.Client") as client:
        assert main([str(media), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "cat.png" in output
    assert "cat.gif" not in output
    client.assert_not_called()
