"""Slash command registration and access-control rules."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from meme_manager.models import Meme
from meme_manager.views import MemePicker

if TYPE_CHECKING:
    from meme_manager.bot import MemeBot

LOG = logging.getLogger(__name__)


def register_commands(bot: MemeBot) -> None:
    group = app_commands.Group(name="meme", description="Search and share saved memes")

    categories = app_commands.Group(
        name="category", description="Quản lý các kênh lưu meme", parent=group
    )

    @categories.command(name="create", description="Tạo hoặc mở kênh theo loại meme")
    @app_commands.describe(name="Tên loại meme, ví dụ reaction hoặc mèo khóc")
    async def create_category(interaction: discord.Interaction, name: str) -> None:
        if not _is_manager(interaction):
            await interaction.response.send_message("Cần quyền Manage Server.", ephemeral=True)
            return
        if interaction.guild is None or interaction.guild.id != bot.settings.guild_id:
            await interaction.response.send_message(
                "Chỉ dùng được trong server đã cấu hình.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            channel = await bot.create_meme_channel(interaction.guild, name)
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
        await _show_picker(bot, interaction, matches)

    @group.command(name="list", description="Browse recently saved memes")
    @app_commands.describe(category="Kênh category muốn xem")
    async def list_memes(
        interaction: discord.Interaction, category: discord.TextChannel | None = None
    ) -> None:
        matches = bot.catalog.search(
            bot.settings.guild_id, channel_id=category.id if category else None
        )
        await _show_picker(bot, interaction, matches)

    @group.command(name="random", description="Send a random saved meme")
    async def random_meme(interaction: discord.Interaction) -> None:
        meme = bot.catalog.random(bot.settings.guild_id)
        if meme is None:
            await interaction.response.send_message("Chưa có meme nào.", ephemeral=True)
            return
        await bot.send_meme(interaction, meme)

    @group.command(name="edit", description="Rename a meme and update its tags")
    async def edit(
        interaction: discord.Interaction, meme_id: int, title: str, tags: str = ""
    ) -> None:
        meme = bot.catalog.get(meme_id, bot.settings.guild_id)
        if meme is None:
            await interaction.response.send_message("Không tìm thấy meme.", ephemeral=True)
            return
        if not _can_manage(interaction, meme):
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
        if not _can_manage(interaction, meme):
            await interaction.response.send_message(
                "Chỉ người upload hoặc quản lý server mới được xóa.", ephemeral=True
            )
            return
        bot.catalog.remove(meme_id, bot.settings.guild_id)
        await interaction.response.send_message(
            "Đã bỏ khỏi danh mục. File gốc trong Discord vẫn giữ nguyên.",
            ephemeral=True,
        )

    @group.command(name="import", description="Nhập meme từ các kênh trong category")
    @app_commands.describe(limit="Số tin nhắn gần nhất mỗi kênh, tối đa 1000")
    async def import_history(interaction: discord.Interaction, limit: int = 200) -> None:
        if not _is_manager(interaction):
            await interaction.response.send_message("Cần quyền Manage Server.", ephemeral=True)
            return
        if interaction.guild is None or interaction.guild.id != bot.settings.guild_id:
            await interaction.response.send_message(
                "Chỉ dùng được trong server đã cấu hình.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            category = await bot.ensure_meme_category(interaction.guild)
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
                "Không chuẩn bị được nhóm Memes. Kiểm tra quyền Manage Channels và View Channel.",
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
                async for message in channel.history(limit=min(max(limit, 1), 1000)):
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

    bot.tree.add_command(group, guild=bot.guild)


async def _show_picker(bot: MemeBot, interaction: discord.Interaction, matches: list[Meme]) -> None:
    if not matches:
        await interaction.response.send_message("Không tìm thấy meme phù hợp.", ephemeral=True)
        return
    view = MemePicker(bot, matches, interaction.user.id)
    await interaction.response.defer(ephemeral=True, thinking=True)
    await view.show_preview(interaction)


def _is_manager(interaction: discord.Interaction) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions is not None and permissions.manage_guild)


def _can_manage(interaction: discord.Interaction, meme: Meme) -> bool:
    return interaction.user.id == meme.author_id or _is_manager(interaction)
