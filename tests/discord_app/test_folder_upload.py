"""File uploads and source recovery mock only the Discord HTTP boundaries."""

import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from meme_manager.config import RuntimeConfig
from meme_manager.discord_app.folder_upload import DiscordFolderUploader
from meme_manager.domain.models import ImportedFile, LocalMeme, Meme
from meme_manager.services.folder_import import UploadError, scan_folder


@pytest.fixture
def source(tmp_path: Path, config: RuntimeConfig) -> LocalMeme:
    (tmp_path / "cat.gif").write_bytes(b"image")
    return scan_folder(tmp_path, media=config.media).files[0]


@pytest.fixture
def uploader() -> DiscordFolderUploader:
    attachment = SimpleNamespace(
        id=40,
        filename="cat.gif",
        content_type="image/gif",
        size=5,
        read=AsyncMock(return_value=b"image"),
    )
    message = SimpleNamespace(
        id=30, author=SimpleNamespace(id=50), content="", attachments=[attachment]
    )
    channel = Mock(spec=discord.TextChannel)
    channel.id = 20
    channel.name = "general"
    channel.guild = SimpleNamespace(id=1)
    channel.category_id = 10
    channel.send = AsyncMock(return_value=message)
    channel.fetch_message = AsyncMock(return_value=message)
    client = Mock(fetch_channel=AsyncMock(return_value=channel))
    guild = Mock(spec=discord.Guild)
    guild.id = 1
    guild.filesize_limit = 1000
    categories = Mock(create_channel=AsyncMock(return_value=channel))
    categories.registry.get_meme_category_id.return_value = 10
    return DiscordFolderUploader(client, guild, categories)


def test_upload_produces_real_reference_metadata_and_closes_file(
    uploader: DiscordFolderUploader, source: LocalMeme
) -> None:
    record = asyncio.run(uploader.upload(source))
    assert (record.guild_id, record.channel_id, record.message_id, record.attachment_id) == (
        1,
        20,
        30,
        40,
    )
    channel = uploader.categories.create_channel.return_value
    sent = channel.send.call_args.kwargs
    assert sent["file"].fp.closed
    assert not sent["allowed_mentions"].everyone
    uploader.categories.create_channel.assert_awaited_once_with(uploader.guild, "general")


def test_oversize_file_does_not_create_channels_or_upload(
    uploader: DiscordFolderUploader, source: LocalMeme
) -> None:
    with pytest.raises(UploadError, match="vượt giới hạn"):
        asyncio.run(uploader.upload(replace(source, file_size=1001)))
    uploader.categories.create_channel.assert_not_awaited()


def test_modified_file_is_rejected_before_upload(
    uploader: DiscordFolderUploader, source: LocalMeme
) -> None:
    source.path.write_bytes(b"changed")
    with pytest.raises(UploadError, match="thay đổi"):
        asyncio.run(uploader.upload(source))
    uploader.categories.create_channel.assert_not_awaited()


def test_permission_error_becomes_a_file_error(
    uploader: DiscordFolderUploader, source: LocalMeme
) -> None:
    uploader.categories.create_channel.side_effect = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "No access"
    )
    with pytest.raises(UploadError, match="HTTP 403"):
        asyncio.run(uploader.upload(source))


def test_recovery_distinguishes_deleted_file_from_permission_failure(
    uploader: DiscordFolderUploader,
) -> None:
    reference = ImportedFile(1, 20, 30, 40)
    uploader.client.fetch_channel.side_effect = discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"), "Deleted"
    )
    assert asyncio.run(uploader.recover(reference)) is None
    uploader.client.fetch_channel.side_effect = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "Forbidden"
    )
    with pytest.raises(UploadError, match="HTTP 403"):
        asyncio.run(uploader.recover(reference))


def test_recovery_rejects_foreign_guild_and_moved_channel(uploader: DiscordFolderUploader) -> None:
    with pytest.raises(UploadError, match="server khác"):
        asyncio.run(uploader.recover(ImportedFile(9, 20, 30, 40)))
    channel = uploader.client.fetch_channel.return_value
    channel.category_id = 99
    with pytest.raises(UploadError, match="ngoài Memes"):
        asyncio.run(uploader.recover(ImportedFile(1, 20, 30, 40)))


def test_matching_old_upload_requires_identical_content_hash(
    uploader: DiscordFolderUploader, source: LocalMeme
) -> None:
    candidate = Mock(spec=Meme)
    candidate.guild_id = 1
    candidate.channel_id = 20
    candidate.message_id = 30
    candidate.attachment_id = 40
    assert asyncio.run(uploader.match_existing(source, candidate)) is not None
    changed = replace(source, content_hash="0" * 64)
    assert asyncio.run(uploader.match_existing(changed, candidate)) is None
    uploader.categories.create_channel.assert_not_awaited()
