"""Rename/tag and unindex memes with author or manager authorization."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from meme_manager.discord_app.commands.permissions import can_manage

if TYPE_CHECKING:
    from meme_manager.discord_app.bot import MemeBot


def register_manage_commands(group: app_commands.Group, bot: MemeBot) -> None:
    @group.command(name="edit", description="Rename a meme and update its tags")
    async def edit(
        interaction: discord.Interaction, meme_id: int, title: str, tags: str = ""
    ) -> None:
        meme = bot.catalog.get(meme_id, bot.settings.guild_id)
        if meme is None:
            await interaction.response.send_message("Không tìm thấy meme.", ephemeral=True)
            return
        if not can_manage(interaction, meme):
            await interaction.response.send_message(
                "Chỉ người upload hoặc quản lý server mới được sửa.", ephemeral=True
            )
            return
        try:
            bot.catalog.update(meme_id, bot.settings.guild_id, title, tags)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message("Đã cập nhật meme.", ephemeral=True)

    @group.command(name="remove", description="Remove a meme from the search index")
    async def remove(interaction: discord.Interaction, meme_id: int) -> None:
        meme = bot.catalog.get(meme_id, bot.settings.guild_id)
        if meme is None:
            await interaction.response.send_message("Không tìm thấy meme.", ephemeral=True)
            return
        if not can_manage(interaction, meme):
            await interaction.response.send_message(
                "Chỉ người upload hoặc quản lý server mới được xóa.", ephemeral=True
            )
            return
        bot.catalog.remove(meme_id, bot.settings.guild_id)
        await interaction.response.send_message(
            "Đã bỏ khỏi danh mục. File gốc trong Discord vẫn giữ nguyên.",
            ephemeral=True,
        )
