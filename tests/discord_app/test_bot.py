"""Category ingestion and import use mocked Discord boundaries, without a token."""

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from meme_manager.config import Settings
from meme_manager.discord_app.bot import MemeBot
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.channels import ChannelRegistry
from meme_manager.persistence.database import SQLiteDatabase
from meme_manager.services.search import MemeSearchService


@pytest.fixture
def bot(database: SQLiteDatabase, catalog: MemeCatalog, channels: ChannelRegistry) -> MemeBot:
    channels.set_meme_category_id(1, 20)
    return MemeBot(
        Settings("test-token", 1, database.path), catalog, channels, MemeSearchService(catalog)
    )


def channel(channel_id: int = 2, category_id: int | None = 20) -> Mock:
    result = Mock(spec=discord.TextChannel)
    result.id = channel_id
    result.category_id = category_id
    result.name = "mèo-khóc"
    return result


def message(source: Mock, guild_id: int = 1, author_bot: bool = False) -> Mock:
    result = Mock(spec=discord.Message)
    result.guild = SimpleNamespace(id=guild_id)
    result.channel = source
    result.id = 3
    result.author = SimpleNamespace(id=4, bot=author_bot)
    result.content = "caption"
    result.attachments = [
        SimpleNamespace(id=source.id * 10, filename="cat.gif", content_type="image/gif", size=10)
    ]
    return result


def test_indexes_multiple_category_channels_and_searches_channel_name(bot: MemeBot) -> None:
    for source in (channel(2), channel(5)):
        asyncio.run(bot.on_message(message(source)))
    assert len(bot.catalog.search(1, "meo khoc")) == 2
    assert {m.channel_id for m in bot.catalog.search(1)} == {2, 5}


@pytest.mark.parametrize(
    ("guild_id", "category_id", "author_bot"),
    [(9, 20, False), (1, 99, False), (1, 20, True)],
)
def test_rejects_wrong_guild_category_and_bot_messages(
    bot: MemeBot, guild_id: int, category_id: int, author_bot: bool
) -> None:
    upload = message(channel(category_id=category_id), guild_id, author_bot)
    asyncio.run(bot.on_message(upload))
    assert bot.index_message(upload) == 0
    assert bot.catalog.search(1) == []


def test_rejects_dm_and_thread(bot: MemeBot) -> None:
    upload = message(channel())
    upload.guild = None
    assert bot.index_message(upload) == 0
    thread = Mock(spec=discord.Thread)
    thread.id = 7
    upload = message(thread)
    assert bot.index_message(upload) == 0


def test_deletion_removes_index_even_after_channel_moves(bot: MemeBot) -> None:
    source = channel()
    bot.index_message(message(source))
    source.category_id = 99
    payload = SimpleNamespace(guild_id=9, channel_id=2, message_id=3)
    asyncio.run(bot.on_raw_message_delete(payload))
    assert len(bot.catalog.search(1)) == 1
    payload.guild_id = 1
    asyncio.run(bot.on_raw_message_delete(payload))
    assert bot.catalog.search(1) == []


def interaction(manager: bool = True) -> Mock:
    result = Mock(spec=discord.Interaction)
    result.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=manager))
    result.guild = Mock(spec=discord.Guild)
    result.guild.id = 1
    result.response = AsyncMock()
    result.followup = AsyncMock()
    return result


def run_import(bot: MemeBot, request: Mock, limit: int = 200) -> None:
    group = bot.tree.get_command("meme", guild=bot.guild)
    command = group.get_command("import")
    asyncio.run(command.callback(request, limit))


def test_import_reads_all_text_channels_and_continues_after_permission_failure(
    bot: MemeBot,
) -> None:
    sources = [channel(2), channel(5), channel(6)]

    async def history(**kwargs: int) -> AsyncIterator[Mock]:
        assert kwargs["limit"] == 1000
        yield message(sources[0])
        yield message(sources[0], author_bot=True)

    async def denied_history(**kwargs: int) -> AsyncIterator[Mock]:
        raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "No access")
        yield  # Make the failing boundary an async iterator, like channel.history.

    async def other_history(**kwargs: int) -> AsyncIterator[Mock]:
        yield message(sources[2])

    sources[0].history.side_effect = history
    sources[1].history.side_effect = denied_history
    sources[2].history.side_effect = other_history
    category = Mock(spec=discord.CategoryChannel)
    category.id = 20
    category.guild = SimpleNamespace(id=1)
    bot.categories.ensure_group = AsyncMock(return_value=category)
    request = interaction()
    request.guild.fetch_channels = AsyncMock(return_value=sources)
    run_import(bot, request, 5000)
    assert len(bot.catalog.search(1)) == 2
    text = request.followup.send.call_args.args[0]
    assert "2 file mới" in text
    assert "1 kênh" in text
    request.response.defer.assert_awaited_once()


def test_import_requires_manager(bot: MemeBot) -> None:
    bot.categories.ensure_group = AsyncMock()
    request = interaction(manager=False)
    run_import(bot, request)
    bot.categories.ensure_group.assert_not_awaited()
    request.response.send_message.assert_awaited_once()


@pytest.mark.parametrize("guild_id", [None, 9])
def test_import_rejects_dm_or_wrong_guild(bot: MemeBot, guild_id: int | None) -> None:
    bot.categories.ensure_group = AsyncMock()
    request = interaction()
    request.guild = None if guild_id is None else SimpleNamespace(id=guild_id)
    run_import(bot, request)
    bot.categories.ensure_group.assert_not_awaited()
    assert "server đã cấu hình" in request.response.send_message.call_args.args[0]


def test_import_empty_category(bot: MemeBot) -> None:
    category = Mock(spec=discord.CategoryChannel)
    category.id = 20
    bot.categories.ensure_group = AsyncMock(return_value=category)
    request = interaction()
    request.guild.fetch_channels = AsyncMock(return_value=[])
    run_import(bot, request)
    assert "/meme category create" in request.followup.send.call_args.args[0]


def test_no_indexing_until_meme_group_is_registered(bot: MemeBot) -> None:
    database = SQLiteDatabase(bot.settings.database_path.parent / "empty.sqlite3")
    database.initialize()
    bot.catalog = MemeCatalog(database)
    bot.channels = ChannelRegistry(database)
    assert bot.index_message(message(channel(category_id=None))) == 0
    assert bot.index_message(message(channel())) == 0


def test_search_uses_fuzzy_service_and_list_keeps_category_filter(bot: MemeBot) -> None:
    bot.index_message(message(channel(2)))
    bot.index_message(message(channel(5)))
    group = bot.tree.get_command("meme", guild=bot.guild)
    request = interaction()
    with patch(
        "meme_manager.discord_app.commands.browse.show_picker", new_callable=AsyncMock
    ) as picker:
        asyncio.run(group.get_command("search").callback(request, "meo khco", channel(5)))
        assert [m.channel_id for m in picker.call_args.args[2]] == [5]
        asyncio.run(group.get_command("list").callback(request, channel(2)))
        assert [m.channel_id for m in picker.call_args.args[2]] == [2]
