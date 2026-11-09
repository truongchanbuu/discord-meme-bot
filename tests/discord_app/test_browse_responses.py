"""Browse commands acknowledge before queries and always edit the deferred response."""

import asyncio
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from meme_manager.discord_app.bot import MemeBot
from meme_manager.domain.models import Meme


def interaction() -> Mock:
    request = Mock(spec=discord.Interaction)
    request.response = AsyncMock()
    request.edit_original_response = AsyncMock()
    request.user = SimpleNamespace(id=50)
    return request


@pytest.mark.parametrize("command_name", ["search", "list"])
def test_acknowledges_before_query_and_edits_empty_response(
    bot: MemeBot, command_name: str
) -> None:
    async def run() -> None:
        request = interaction()
        acknowledged = Event()
        loop_thread = get_ident()

        async def defer(**kwargs: object) -> None:
            acknowledged.set()

        def query(*args: object, **kwargs: object) -> list[Meme]:
            assert acknowledged.is_set(), "The interaction must be deferred before querying"
            assert get_ident() != loop_thread, "Search must not block the gateway event loop"
            return []

        request.response.defer.side_effect = defer
        if command_name == "search":
            bot.search_service.search = Mock(side_effect=query)
        else:
            bot.catalog.search = Mock(side_effect=query)
        command = bot.tree.get_command("meme", guild=bot.guild).get_command(command_name)
        if command_name == "search":
            await command.callback(request, "no match")
        else:
            await command.callback(request)
        request.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        request.response.send_message.assert_not_awaited()
        request.edit_original_response.assert_awaited_once_with(
            content="Không tìm thấy meme phù hợp."
        )

    asyncio.run(run())


@pytest.mark.parametrize("command_name", ["search", "list"])
def test_populated_results_do_not_acknowledge_twice(bot: MemeBot, command_name: str) -> None:
    async def run() -> None:
        request = interaction()
        matches = [Mock(spec=Meme)]
        if command_name == "search":
            bot.search_service.search = Mock(return_value=matches)
        else:
            bot.catalog.search = Mock(return_value=matches)
        command = bot.tree.get_command("meme", guild=bot.guild).get_command(command_name)
        with patch("meme_manager.discord_app.commands.browse.MemePicker") as picker:
            picker.return_value.show_preview = AsyncMock()
            if command_name == "search":
                await command.callback(request, "cat")
            else:
                await command.callback(request)
            picker.assert_called_once_with(
                bot.media, matches, request.user.id, options=bot.settings.config.bot
            )
            picker.return_value.show_preview.assert_awaited_once_with(request)
        request.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        request.response.send_message.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize("command_name", ["search", "list"])
@pytest.mark.parametrize("file_type", [None, "jpg", "video"])
def test_browse_file_filter_is_passed_with_category(
    bot: MemeBot, command_name: str, file_type: str | None
) -> None:
    async def run() -> None:
        request = interaction()
        query = Mock(return_value=[])
        if command_name == "search":
            bot.search_service.search = query
        else:
            bot.catalog.search = query
        command = bot.tree.get_command("meme", guild=bot.guild).get_command(command_name)
        selected_category = SimpleNamespace(id=123)
        if command_name == "search":
            await command.callback(request, "votay", selected_category, file_type)
        else:
            await command.callback(request, selected_category, file_type)
        assert query.call_args.kwargs == {
            "channel_id": 123,
            "extensions": bot.settings.config.media.extensions_for(file_type),
        }
        option = next(p for p in command.parameters if p.name == "file_type")
        assert [c.value for c in option.choices] == [
            t.name for t in bot.settings.config.media.types
        ]
        assert not option.required

    asyncio.run(run())
