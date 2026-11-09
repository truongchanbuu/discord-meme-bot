"""Manager-only category creation and history import."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from meme_manager.discord_app.commands.permissions import is_manager

if TYPE_CHECKING:
    from meme_manager.discord_app.bot import MemeBot

LOG = logging.getLogger(__name__)


def register_category_commands(group: app_commands.Group, bot: MemeBot) -> None:
    categories = app_commands.Group(
        name="category", description="Quản lý các kênh lưu meme", parent=group
    )

    @categories.command(name="create", description="Tạo hoặc mở kênh theo loại meme")
    @app_commands.describe(name="Tên loại meme, ví dụ reaction hoặc mèo khóc")
    async def create_category(interaction: discord.Interaction, name: str) -> None:
        if not is_manager(interaction):
            await interaction.response.send_message("Cần quyền Manage Server.", ephemeral=True)
            return
        if interaction.guild is None or interaction.guild.id != bot.settings.guild_id:
            await interaction.response.send_message(
                "Chỉ dùng được trong server đã cấu hình.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            channel = await bot.categories.create_channel(interaction.guild, name)
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except discord.HTTPException:
            LOG.exception("Could not create meme channel")
            await interaction.followup.send(
                "Không tạo hoặc đọc được kênh. Kiểm tra quyền Manage Channels và View Channel "
                "của bot rồi thử lại.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"Kênh meme đã sẵn sàng: {channel.mention}. Hãy upload meme vào kênh này.",
            ephemeral=True,
        )

    @group.command(name="import", description="Nhập meme từ các kênh trong category")
    @app_commands.describe(
        limit=f"Số tin nhắn gần nhất mỗi kênh, tối đa {bot.settings.config.bot.history_max}"
    )
    async def import_history(
        interaction: discord.Interaction, limit: int = bot.settings.config.bot.history_default
    ) -> None:
        if not is_manager(interaction):
            await interaction.response.send_message("Cần quyền Manage Server.", ephemeral=True)
            return
        if interaction.guild is None or interaction.guild.id != bot.settings.guild_id:
            await interaction.response.send_message(
                "Chỉ dùng được trong server đã cấu hình.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            category = await bot.categories.ensure_group(interaction.guild)
            channels = [
                channel
                for channel in await interaction.guild.fetch_channels()
                if isinstance(channel, discord.TextChannel) and channel.category_id == category.id
            ]
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except discord.HTTPException:
            LOG.exception("Failed fetching meme category")
            await interaction.followup.send(
                "Không chuẩn bị được nhóm thư viện meme. Kiểm tra quyền Manage Channels và View Channel.",
                ephemeral=True,
            )
            return
        if not channels:
            await interaction.followup.send(
                "Chưa có kênh meme. Dùng /meme category create để tạo kênh đầu tiên.",
                ephemeral=True,
            )
            return
        added = 0
        skipped = 0
        for channel in channels:
            try:
                async for message in channel.history(
                    limit=min(max(limit, 1), bot.settings.config.bot.history_max)
                ):
                    added += bot.index_message(message)
            except discord.HTTPException:
                skipped += 1
                LOG.exception("Failed importing channel %s", channel.id)
        result = f"Đã index {added} file mới từ {len(channels)} kênh."
        if skipped:
            result += (
                f" Có {skipped} kênh đọc chưa đầy đủ hoặc không đọc được."
                " Kiểm tra quyền View Channel và Read Message History rồi thử lại."
            )
        await interaction.followup.send(result, ephemeral=True)
