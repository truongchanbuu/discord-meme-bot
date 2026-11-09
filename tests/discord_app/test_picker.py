"""Private picker previews render images/GIFs and upload playable video attachments."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from meme_manager.config import RuntimeConfig
from meme_manager.discord_app.commands.browse import show_picker
from meme_manager.discord_app.picker import MemeOption, MemePicker
from meme_manager.domain.models import Meme


def meme(kind: str = "image", filename: str = "cat.gif") -> Meme:
    return Meme(
        id=1,
        guild_id=10,
        channel_id=20,
        message_id=30,
        attachment_id=40,
        author_id=50,
        filename=filename,
        title="Mèo khóc",
        tags="reaction",
        message_text="",
        media_kind=kind,
        content_type="video/mp4" if kind == "video" else "image/gif",
        file_size=100,
    )


def attachment(filename: str = "cat.gif", size: int = 100) -> Mock:
    result = Mock(spec=discord.Attachment)
    result.url = "https://cdn.discordapp.com/attachments/fresh-media"
    result.size = size
    file = Mock(spec=discord.File)
    file.filename = filename
    result.to_file = AsyncMock(return_value=file)
    return result


def interaction() -> Mock:
    result = Mock(spec=discord.Interaction)
    result.guild = SimpleNamespace(filesize_limit=1000)
    result.filesize_limit = 1000
    result.user = SimpleNamespace(id=50)
    result.response = AsyncMock()
    result.followup = AsyncMock()
    result.edit_original_response = AsyncMock()
    return result


@pytest.mark.parametrize("filename", ["cat.gif", "cat.png", "cat.webp"])
def test_image_and_gif_preview_uses_fresh_image_url(filename: str, config: RuntimeConfig) -> None:
    async def run() -> None:
        original = attachment(filename)
        bot = Mock(get_attachment=AsyncMock(return_value=original))
        view = MemePicker(bot, [meme(filename=filename)], 50, options=config.bot)
        embed, files = await view.preview(1000)
        assert embed.image.url == original.url
        assert files == []
        original.to_file.assert_not_awaited()
        assert str(embed.footer.text) == "Trang 1/1"

    asyncio.run(run())


def test_video_preview_edits_the_previously_deferred_private_response(
    config: RuntimeConfig,
) -> None:
    async def run() -> None:
        original = attachment("cat.mp4")
        bot = Mock(get_attachment=AsyncMock(return_value=original))
        request = interaction()
        await show_picker(
            Mock(media=bot, settings=Mock(config=config)), request, [meme("video", "cat.mp4")]
        )
        request.response.defer.assert_not_awaited()
        payload = request.edit_original_response.call_args.kwargs
        assert payload["attachments"][0].filename == "cat.mp4"
        payload["attachments"][0].close.assert_called_once()
        assert payload["view"].requester_id == request.user.id
        assert not payload["embed"].image.url
        original.to_file.assert_awaited_once_with(use_cached=False)
        request.followup.send.assert_not_awaited()

    asyncio.run(run())


def test_switching_from_video_to_image_removes_previous_attachment(config: RuntimeConfig) -> None:
    async def run() -> None:
        video = meme("video", "cat.mp4")
        image = replace(meme(), id=2)
        bot = Mock(get_attachment=AsyncMock(side_effect=[attachment("cat.mp4"), attachment()]))
        view = MemePicker(bot, [video, image], 50, options=config.bot)
        request = interaction()
        await view.show_preview(request)
        assert len(request.edit_original_response.call_args.kwargs["attachments"]) == 1
        selector = next(item for item in view.children if isinstance(item, MemeOption))
        selector._values = [str(image.id)]
        await selector.callback(request)
        request.response.defer.assert_awaited_once()
        assert request.edit_original_response.call_args.kwargs["attachments"] == []
        assert request.edit_original_response.call_args.kwargs["embed"].image.url
        assert view.selected_id == image.id

    asyncio.run(run())


def test_oversize_video_has_source_link_without_download(config: RuntimeConfig) -> None:
    async def run() -> None:
        original = attachment("cat.mp4", size=1001)
        video = meme("video", "cat.mp4")
        view = MemePicker(
            Mock(get_attachment=AsyncMock(return_value=original)), [video], 50, options=config.bot
        )
        embed, files = await view.preview(1000)
        assert files == []
        assert video.jump_url in embed.description
        assert "vượt giới hạn" in embed.fields[0].name
        original.to_file.assert_not_awaited()

    asyncio.run(run())


def test_deleted_media_clears_old_preview(config: RuntimeConfig) -> None:
    async def run() -> None:
        view = MemePicker(
            Mock(get_attachment=AsyncMock(return_value=None)), [meme()], 50, options=config.bot
        )
        request = interaction()
        await view.show_preview(request)
        payload = request.edit_original_response.call_args.kwargs
        assert payload["attachments"] == []
        assert not payload["embed"].image.url
        assert "File gốc đã mất" in payload["embed"].fields[0].value

    asyncio.run(run())


def test_failed_video_download_falls_back_to_source_link(config: RuntimeConfig) -> None:
    async def run() -> None:
        original = attachment("cat.mp4")
        original.to_file.side_effect = discord.NotFound(
            SimpleNamespace(status=404, reason="Not Found"), "Missing attachment"
        )
        video = meme("video", "cat.mp4")
        view = MemePicker(
            Mock(get_attachment=AsyncMock(return_value=original)), [video], 50, options=config.bot
        )
        embed, files = await view.preview(1000)
        assert files == []
        assert embed.fields[0].name == "Không tải được video"
        assert video.jump_url in embed.description

    asyncio.run(run())


def test_failed_preview_upload_clears_media_and_closes_file(config: RuntimeConfig) -> None:
    async def run() -> None:
        original = attachment("cat.mp4")
        view = MemePicker(
            Mock(get_attachment=AsyncMock(return_value=original)),
            [meme("video", "cat.mp4")],
            50,
            options=config.bot,
        )
        request = interaction()
        request.edit_original_response.side_effect = [
            discord.HTTPException(SimpleNamespace(status=413, reason="Too Large"), "Upload failed"),
            None,
        ]
        await view.show_preview(request)
        assert request.edit_original_response.await_count == 2
        first, second = request.edit_original_response.call_args_list
        first.kwargs["attachments"][0].close.assert_called_once()
        assert second.kwargs["attachments"] == []
        assert "Không tải được preview" in second.kwargs["embed"].fields[0].name

    asyncio.run(run())


def test_next_previous_and_requester_authorization(config: RuntimeConfig) -> None:
    async def run() -> None:
        originals = [replace(meme(), id=index) for index in range(1, 7)]
        bot = Mock(get_attachment=AsyncMock(return_value=attachment()))
        view = MemePicker(bot, originals, 50, options=config.bot)
        request = interaction()
        assert await view.interaction_check(request)
        request.user.id = 99
        assert not await view.interaction_check(request)
        request.response.send_message.assert_awaited_once()
        await view.next_page.callback(request)
        assert view.page == 1
        assert view.selected_id == 6
        assert request.edit_original_response.call_args.kwargs["attachments"] == []
        await view.previous_page.callback(request)
        assert view.page == 0
        assert view.selected_id == 1

    asyncio.run(run())


def test_effective_interaction_limit_is_used_for_video_preview(config: RuntimeConfig) -> None:
    async def run() -> None:
        original = attachment("cat.mp4", size=100)
        view = MemePicker(
            Mock(get_attachment=AsyncMock(return_value=original)),
            [meme("video", "cat.mp4")],
            50,
            options=config.bot,
        )
        request = interaction()
        request.filesize_limit = 50
        await view.show_preview(request)
        assert request.edit_original_response.call_args.kwargs["attachments"] == []
        original.to_file.assert_not_awaited()

    asyncio.run(run())


def test_slow_video_preview_cannot_overwrite_newer_image_selection(config: RuntimeConfig) -> None:
    async def run() -> None:
        video = meme("video", "cat.mp4")
        image = replace(meme(), id=2)
        started = asyncio.Event()
        release = asyncio.Event()

        async def get_attachment(selected: Meme) -> Mock:
            if selected.id == video.id:
                started.set()
                await release.wait()
                return attachment("cat.mp4")
            return attachment()

        view = MemePicker(
            Mock(get_attachment=AsyncMock(side_effect=get_attachment)),
            [video, image],
            50,
            options=config.bot,
        )
        request = interaction()
        slow = asyncio.create_task(view.show_preview(request))
        await started.wait()
        view.selected_id = image.id
        newer = asyncio.create_task(view.show_preview(request))
        await asyncio.sleep(0)
        assert not newer.done()
        release.set()
        await asyncio.gather(slow, newer)
        assert request.edit_original_response.await_count == 2
        latest = request.edit_original_response.call_args.kwargs
        assert latest["embed"].title.startswith("#2")
        assert latest["attachments"] == []
        assert latest["embed"].image.url

    asyncio.run(run())
