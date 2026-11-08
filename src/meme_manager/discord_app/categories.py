"""Create and recover the library group and its meme category channels."""

import asyncio

import discord

from meme_manager.domain.repositories import ChannelRepository
from meme_manager.domain.text import meme_channel_name


class CategoryManager:
    def __init__(self, guild_id: int, registry: ChannelRepository) -> None:
        self.guild_id = guild_id
        self.registry = registry
        self._category_lock = asyncio.Lock()
        self._channel_lock = asyncio.Lock()

    async def ensure_group(self, guild: discord.Guild) -> discord.CategoryChannel:
        """Recover the persisted category or create it once, including after reconnects."""
        if guild.id != self.guild_id:
            raise ValueError("Chỉ dùng được trong server đã cấu hình.")
        async with self._category_lock:
            channels = await guild.fetch_channels()
            category_id = self.registry.get_meme_category_id(guild.id)
            saved = next((channel for channel in channels if channel.id == category_id), None)
            if saved is not None:
                if not isinstance(saved, discord.CategoryChannel):
                    raise ValueError("Nhóm Memes đã lưu không còn là category.")
                return saved
            matches = [
                channel
                for channel in channels
                if isinstance(channel, discord.CategoryChannel) and channel.name == "Memes"
            ]
            if len(matches) > 1:
                raise ValueError(
                    "Có nhiều nhóm tên Memes. Hãy giữ một nhóm mang tên này rồi thử lại."
                )
            category = (
                matches[0]
                if matches
                else await guild.create_category("Memes", reason="Thiết lập thư viện meme")
            )
            self.registry.set_meme_category_id(guild.id, category.id)
            return category

    async def create_channel(self, guild: discord.Guild, name: str) -> discord.TextChannel:
        """Create or recover a category channel without duplicating concurrent requests."""
        name = meme_channel_name(name)
        category = await self.ensure_group(guild)
        async with self._channel_lock:
            channels = await guild.fetch_channels()
            saved_id = self.registry.get_meme_channel_id(guild.id, name)
            saved = next((channel for channel in channels if channel.id == saved_id), None)
            if saved is not None:
                if not isinstance(saved, discord.TextChannel) or saved.category_id != category.id:
                    raise ValueError(
                        "Kênh đã lưu nằm ngoài nhóm Memes. Hãy chuyển kênh về nhóm này."
                    )
                return saved
            matches = [
                channel
                for channel in channels
                if isinstance(channel, discord.TextChannel)
                and channel.category_id == category.id
                and channel.name == name
            ]
            if len(matches) > 1:
                raise ValueError(
                    "Có nhiều kênh cùng tên trong Memes. Hãy đổi tên kênh trùng rồi thử lại."
                )
            channel = (
                matches[0]
                if matches
                else await guild.create_text_channel(
                    name, category=category, reason="Tạo category meme"
                )
            )
            self.registry.set_meme_channel_id(guild.id, name, channel.id)
            return channel
