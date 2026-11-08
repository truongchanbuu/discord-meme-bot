"""Search, browse and share memes through the private picker."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from meme_manager.discord_app.picker import MemePicker
from meme_manager.domain.models import Meme

if TYPE_CHECKING:
    from meme_manager.discord_app.bot import MemeBot


def register_browse_commands(group: app_commands.Group, bot: MemeBot) -> None:
    @group.command(name="search", description="Tìm meme theo tên, mô tả, tag hoặc tên kênh")
    @app_commands.describe(
        query="Tên, mô tả hoặc tag (không dấu cũng được)",
        category="Kênh category để giới hạn kết quả",
    )
    async def search(
        interaction: discord.Interaction, query: str, category: discord.TextChannel | None = None
    ) -> None:
        matches = bot.catalog.search(
            bot.settings.guild_id, query, channel_id=category.id if category else None
        )
        await show_picker(bot, interaction, matches)

    @group.command(name="list", description="Browse recently saved memes")
    @app_commands.describe(category="Kênh category muốn xem")
    async def list_memes(
        interaction: discord.Interaction, category: discord.TextChannel | None = None
    ) -> None:
        matches = bot.catalog.search(
            bot.settings.guild_id, channel_id=category.id if category else None
        )
        await show_picker(bot, interaction, matches)

    @group.command(name="random", description="Send a random saved meme")
    async def random_meme(interaction: discord.Interaction) -> None:
        meme = bot.catalog.random(bot.settings.guild_id)
        if meme is None:
            await interaction.response.send_message("Chưa có meme nào.", ephemeral=True)
            return
        await bot.media.send_meme(interaction, meme)


async def show_picker(bot: MemeBot, interaction: discord.Interaction, matches: list[Meme]) -> None:
    if not matches:
        await interaction.response.send_message("Không tìm thấy meme phù hợp.", ephemeral=True)
        return
    view = MemePicker(bot.media, matches, interaction.user.id)
    await interaction.response.defer(ephemeral=True, thinking=True)
    await view.show_preview(interaction)
