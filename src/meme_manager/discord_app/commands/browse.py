"""Search, browse and share memes through the private picker."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from meme_manager.discord_app.picker import MemePicker
from meme_manager.domain.models import Meme

if TYPE_CHECKING:
    from meme_manager.discord_app.bot import MemeBot


def register_browse_commands(group: app_commands.Group, bot: MemeBot) -> None:
    file_choices = [
        app_commands.Choice(
            name=f"{item.name} ({', '.join(item.extensions)})"[:100], value=item.name
        )
        for item in bot.settings.config.media.types
    ]

    @group.command(name="search", description="Tìm meme theo tên, mô tả, tag hoặc tên kênh")
    @app_commands.describe(
        query="Tên, mô tả hoặc tag; hỗ trợ không dấu và lỗi gõ gần đúng",
        category="Kênh category để giới hạn kết quả",
        file_type="Định dạng file muốn tìm",
    )
    @app_commands.choices(file_type=file_choices)
    async def search(
        interaction: discord.Interaction,
        query: str,
        category: discord.TextChannel | None = None,
        file_type: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        matches = await asyncio.to_thread(
            bot.search_service.search,
            bot.settings.guild_id,
            query,
            channel_id=category.id if category else None,
            extensions=bot.settings.config.media.extensions_for(file_type),
        )
        await show_picker(bot, interaction, matches)

    @group.command(name="list", description="Browse recently saved memes")
    @app_commands.describe(category="Kênh category muốn xem", file_type="Định dạng file muốn xem")
    @app_commands.choices(file_type=file_choices)
    async def list_memes(
        interaction: discord.Interaction,
        category: discord.TextChannel | None = None,
        file_type: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        matches = await asyncio.to_thread(
            bot.catalog.search,
            bot.settings.guild_id,
            channel_id=category.id if category else None,
            extensions=bot.settings.config.media.extensions_for(file_type),
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
        await interaction.edit_original_response(content="Không tìm thấy meme phù hợp.")
        return
    view = MemePicker(bot.media, matches, interaction.user.id, options=bot.settings.config.bot)
    await view.show_preview(interaction)
