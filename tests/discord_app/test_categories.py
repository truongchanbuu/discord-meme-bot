"""Bot-managed Discord channels are persisted, recoverable, and manager-only."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from meme_manager.discord_app.bot import MemeBot
from meme_manager.domain.text import meme_channel_name
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.channels import ChannelRegistry
from meme_manager.persistence.database import SQLiteDatabase


def category(category_id: int = 20, name: str = "Memes") -> Mock:
    result = Mock(spec=discord.CategoryChannel)
    result.id = category_id
    result.name = name
    return result


def text_channel(channel_id: int = 30, name: str = "reaction", parent_id: int = 20) -> Mock:
    result = Mock(spec=discord.TextChannel)
    result.id = channel_id
    result.name = name
    result.category_id = parent_id
    result.mention = f"<#{channel_id}>"
    return result


def guild(channels: list[Mock]) -> Mock:
    result = Mock(spec=discord.Guild)
    result.id = 1
    result.fetch_channels = AsyncMock(side_effect=lambda: list(channels))

    async def create_category(name: str, **kwargs: object) -> Mock:
        await asyncio.sleep(0)
        created = category(name=name)
        channels.append(created)
        return created

    async def create_text_channel(name: str, **kwargs: object) -> Mock:
        await asyncio.sleep(0)
        channel_id = 30 + sum(isinstance(item, discord.TextChannel) for item in channels)
        created = text_channel(channel_id=channel_id, name=name)
        channels.append(created)
        return created

    result.create_category = AsyncMock(side_effect=create_category)
    result.create_text_channel = AsyncMock(side_effect=create_text_channel)
    return result


def test_creates_group_and_channel_and_reuses_after_restart(bot: MemeBot) -> None:
    server = guild([])
    created = asyncio.run(bot.categories.create_channel(server, "Reaction"))
    assert created.name == "reaction"
    assert bot.channels.get_meme_category_id(1) == 20
    assert bot.channels.get_meme_channel_id(1, "reaction") == 30
    assert bot.channels.get_meme_category_id(9) is None
    assert bot.channels.get_meme_channel_id(9, "reaction") is None
    reopened = SQLiteDatabase(bot.settings.database_path)
    reopened.initialize()
    restarted = MemeBot(bot.settings, MemeCatalog(reopened), ChannelRegistry(reopened))
    assert asyncio.run(restarted.categories.create_channel(server, "Reaction")) is created
    server.create_category.assert_awaited_once()
    server.create_text_channel.assert_awaited_once()
    assert server.create_text_channel.call_args.kwargs["category"].id == 20


def test_each_new_meme_category_gets_its_own_channel(bot: MemeBot) -> None:
    server = guild([])
    reaction = asyncio.run(bot.categories.create_channel(server, "reaction"))
    cat = asyncio.run(bot.categories.create_channel(server, "Mèo Khóc"))
    assert reaction.id != cat.id
    assert bot.channels.get_meme_channel_id(1, "reaction") == reaction.id
    assert bot.channels.get_meme_channel_id(1, "meo-khoc") == cat.id
    server.create_category.assert_awaited_once()
    assert server.create_text_channel.await_count == 2


def test_recovers_existing_group_and_child_by_name(bot: MemeBot) -> None:
    group = category()
    child = text_channel()
    server = guild([group, child])
    assert asyncio.run(bot.categories.create_channel(server, "reaction")) is child
    server.create_category.assert_not_awaited()
    server.create_text_channel.assert_not_awaited()
    assert bot.channels.get_meme_category_id(1) == group.id
    assert bot.channels.get_meme_channel_id(1, "reaction") == child.id


def test_reuses_saved_ids_after_discord_rename(bot: MemeBot) -> None:
    bot.channels.set_meme_category_id(1, 20)
    bot.channels.set_meme_channel_id(1, "reaction", 30)
    group = category(name="Renamed group")
    child = text_channel(name="renamed-channel")
    server = guild([group, child])
    assert asyncio.run(bot.categories.create_channel(server, "reaction")) is child
    server.create_category.assert_not_awaited()
    server.create_text_channel.assert_not_awaited()


def test_recreates_deleted_group_and_child(bot: MemeBot) -> None:
    bot.channels.set_meme_category_id(1, 999)
    bot.channels.set_meme_channel_id(1, "reaction", 998)
    server = guild([])
    asyncio.run(bot.categories.create_channel(server, "reaction"))
    assert bot.channels.get_meme_category_id(1) == 20
    assert bot.channels.get_meme_channel_id(1, "reaction") == 30


def test_concurrent_creates_do_not_duplicate_channels(bot: MemeBot) -> None:
    server = guild([])

    async def create_twice() -> list[discord.TextChannel]:
        return await asyncio.gather(
            bot.categories.create_channel(server, "Reaction"),
            bot.categories.create_channel(server, "reaction"),
        )

    first, second = asyncio.run(create_twice())
    assert first.id == second.id
    server.create_category.assert_awaited_once()
    server.create_text_channel.assert_awaited_once()


def test_group_in_other_guild_is_rejected_before_api_call(bot: MemeBot) -> None:
    server = guild([])
    server.id = 9
    with pytest.raises(ValueError, match="server đã cấu hình"):
        asyncio.run(bot.categories.create_channel(server, "reaction"))
    server.fetch_channels.assert_not_awaited()


def test_moved_saved_channel_is_not_duplicated_or_moved_back(bot: MemeBot) -> None:
    bot.channels.set_meme_category_id(1, 20)
    bot.channels.set_meme_channel_id(1, "reaction", 30)
    server = guild([category(), text_channel(parent_id=99)])
    with pytest.raises(ValueError, match="nằm ngoài"):
        asyncio.run(bot.categories.create_channel(server, "reaction"))
    server.create_text_channel.assert_not_awaited()


@pytest.mark.parametrize("children", [False, True])
def test_ambiguous_names_require_resolution(bot: MemeBot, children: bool) -> None:
    channels = (
        [category(), text_channel(), text_channel(31)] if children else [category(), category(21)]
    )
    server = guild(channels)
    with pytest.raises(ValueError, match="nhiều"):
        asyncio.run(bot.categories.create_channel(server, "reaction"))
    server.create_category.assert_not_awaited()
    server.create_text_channel.assert_not_awaited()


def test_existing_same_name_outside_group_is_not_adopted(bot: MemeBot) -> None:
    server = guild([category(), text_channel(40, parent_id=99)])
    created = asyncio.run(bot.categories.create_channel(server, "reaction"))
    assert created.id != 40
    assert created.category_id == 20
    server.create_text_channel.assert_awaited_once()


@pytest.mark.parametrize("value", ["", "  ", "🎉", "a" * 101])
def test_invalid_names_are_rejected_before_api_call(bot: MemeBot, value: str) -> None:
    server = guild([])
    with pytest.raises(ValueError, match="Tên category"):
        asyncio.run(bot.categories.create_channel(server, value))
    server.fetch_channels.assert_not_awaited()


def test_vietnamese_name_is_canonical() -> None:
    assert meme_channel_name("  Mèo_Khóc !!! ") == "meo-khoc"


def request(manager: bool = True, guild_id: int | None = 1) -> Mock:
    result = Mock(spec=discord.Interaction)
    result.user = SimpleNamespace(guild_permissions=SimpleNamespace(manage_guild=manager))
    result.guild = None if guild_id is None else SimpleNamespace(id=guild_id)
    result.response = AsyncMock()
    result.followup = AsyncMock()
    return result


def run_create(bot: MemeBot, interaction: Mock, name: str = "reaction") -> None:
    group = bot.tree.get_command("meme", guild=bot.guild)
    command = group.get_command("category").get_command("create")
    asyncio.run(command.callback(interaction, name))


@pytest.mark.parametrize("manager, guild_id", [(False, 1), (True, 9), (True, None)])
def test_command_denies_unprivileged_or_wrong_guild(
    bot: MemeBot, manager: bool, guild_id: int | None
) -> None:
    bot.categories.create_channel = AsyncMock()
    interaction = request(manager, guild_id)
    run_create(bot, interaction)
    bot.categories.create_channel.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.call_args.kwargs["ephemeral"]


def test_command_returns_ephemeral_channel_link(bot: MemeBot) -> None:
    bot.categories.create_channel = AsyncMock(return_value=text_channel())
    interaction = request()
    run_create(bot, interaction)
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert "<#30>" in interaction.followup.send.call_args.args[0]
    assert interaction.followup.send.call_args.kwargs["ephemeral"]


def test_command_reports_missing_bot_permissions(bot: MemeBot) -> None:
    error = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "No access")
    bot.categories.create_channel = AsyncMock(side_effect=error)
    interaction = request()
    run_create(bot, interaction)
    assert "Manage Channels" in interaction.followup.send.call_args.args[0]


def test_command_reports_invalid_name(bot: MemeBot) -> None:
    interaction = request()
    run_create(bot, interaction, "🎉")
    assert "Tên category" in interaction.followup.send.call_args.args[0]


def test_permission_failure_does_not_persist_group_or_create_child(bot: MemeBot) -> None:
    server = guild([])
    server.create_category.side_effect = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "No access"
    )
    with pytest.raises(discord.Forbidden):
        asyncio.run(bot.categories.create_channel(server, "reaction"))
    assert bot.channels.get_meme_category_id(1) is None
    assert bot.channels.get_meme_channel_id(1, "reaction") is None
    server.create_text_channel.assert_not_awaited()


def test_startup_is_idempotent_and_creates_group(bot: MemeBot) -> None:
    server = guild([])
    bot.get_guild = Mock(return_value=server)
    asyncio.run(bot.on_ready())
    asyncio.run(bot.on_ready())
    server.create_category.assert_awaited_once()
    assert bot.channels.get_meme_category_id(1) == 20


def test_startup_permission_failure_is_logged(
    bot: MemeBot, caplog: pytest.LogCaptureFixture
) -> None:
    server = guild([])
    server.fetch_channels.side_effect = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "No access"
    )
    bot.get_guild = Mock(return_value=server)
    asyncio.run(bot.on_ready())
    assert "Could not prepare Memes" in caplog.text
    assert bot.channels.get_meme_category_id(1) is None
