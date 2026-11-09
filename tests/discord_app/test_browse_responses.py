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
            picker.assert_called_once_with(bot.media, matches, request.user.id)
            picker.return_value.show_preview.assert_awaited_once_with(request)
        request.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        request.response.send_message.assert_not_awaited()

    asyncio.run(run())
