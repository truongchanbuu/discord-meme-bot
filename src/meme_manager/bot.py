"""Discord gateway adapter: the entire UI lives in Discord slash commands and buttons."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

from meme_manager.catalog import MemeCatalog
from meme_manager.commands import register_commands
from meme_manager.config import Settings
from meme_manager.models import Meme, MemeInput
from meme_manager.text import meme_channel_name

LOG = logging.getLogger(__name__)


class MemeBot(discord.Client):
    def __init__(self, settings: Settings, catalog: MemeCatalog) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read uploaded attachments and captions.
        super().__init__(intents=intents)
        self.settings = settings
        self.catalog = catalog
        self.tree = app_commands.CommandTree(self)
        self.guild = discord.Object(id=settings.guild_id)
        self._category_lock = asyncio.Lock()
        self._channel_lock = asyncio.Lock()
        register_commands(self)

    async def setup_hook(self) -> None:
        await self.tree.sync(guild=self.guild)
        LOG.info("Synced meme commands for guild %s", self.settings.guild_id)

    async def on_ready(self) -> None:
        LOG.info("Bot online as %s", self.user)
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            LOG.error("Bot cannot access the configured guild %s", self.settings.guild_id)
            return
        try:
            await self.ensure_meme_category(guild)
        except (discord.HTTPException, ValueError):
            LOG.exception(
                "Could not prepare Memes category; check Manage Channels and View Channel"
            )

    async def ensure_meme_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        """Recover the persisted category or create it once, including after reconnects."""
        if guild.id != self.settings.guild_id:
            raise ValueError("Chỉ dùng được trong server đã cấu hình.")
        async with self._category_lock:
            channels = await guild.fetch_channels()
            category_id = self.catalog.get_meme_category_id(guild.id)
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
            self.catalog.set_meme_category_id(guild.id, category.id)
            return category

    async def create_meme_channel(self, guild: discord.Guild, name: str) -> discord.TextChannel:
        """Create or recover a category channel without duplicating concurrent requests."""
        name = meme_channel_name(name)
        category = await self.ensure_meme_category(guild)
        async with self._channel_lock:
            channels = await guild.fetch_channels()
            saved_id = self.catalog.get_meme_channel_id(guild.id, name)
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
            self.catalog.set_meme_channel_id(guild.id, name, channel.id)
            return channel

    async def on_message(self, message: discord.Message) -> None:
        indexed = self.index_message(message)
        if indexed:
            LOG.info("Indexed %s attachment(s) from message %s", indexed, message.id)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id != self.settings.guild_id:
            return
        self.catalog.remove_message(self.settings.guild_id, payload.channel_id, payload.message_id)

    def index_message(self, message: discord.Message) -> int:
        if message.guild is None or message.guild.id != self.settings.guild_id:
            return 0
        if not isinstance(message.channel, discord.TextChannel):
            return 0
        category_id = self.catalog.get_meme_category_id(self.settings.guild_id)
        if category_id is None or message.channel.category_id != category_id or message.author.bot:
            return 0
        added = 0
        for attachment in message.attachments:
            record = MemeInput(
                guild_id=message.guild.id,
                channel_id=message.channel.id,
                message_id=message.id,
                attachment_id=attachment.id,
                author_id=message.author.id,
                filename=attachment.filename,
                content_type=attachment.content_type,
                file_size=attachment.size,
                message_text=message.content,
                channel_name=message.channel.name,
            )
            added += int(self.catalog.add(record))
        return added

    async def get_attachment(self, meme: Meme) -> discord.Attachment | None:
        """Fetch a fresh attachment URL instead of persisting an expiring CDN link."""
        try:
            channel = self.get_channel(meme.channel_id) or await self.fetch_channel(meme.channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                return None
            message = await channel.fetch_message(meme.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
        return next(
            (item for item in message.attachments if item.id == meme.attachment_id),
            None,
        )

    async def send_meme(self, interaction: discord.Interaction, meme: Meme) -> None:
        """Send the original image/video in the active Discord channel."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.followup.send(
                "Không thể gửi meme vào loại channel này.", ephemeral=True
            )
            return
        attachment = await self.get_attachment(meme)
        if attachment is None:
            await interaction.followup.send(
                "File gốc không còn truy cập được. Hãy kiểm tra tin nhắn lưu meme.",
                ephemeral=True,
            )
            return
        try:
            # Stream the freshly retrieved attachment into an uploaded Discord file.
            file = await attachment.to_file(use_cached=False)
            await channel.send(file=file)
        except discord.HTTPException:
            LOG.exception("Could not resend meme %s", meme.id)
            await interaction.followup.send(
                f"Không thể gửi file (có thể vượt giới hạn upload). "
                f"[Xem file gốc]({meme.jump_url}).",
                ephemeral=True,
            )
            return
        await interaction.followup.send("Đã gửi meme vào channel!", ephemeral=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_environment()
    catalog = MemeCatalog(settings.database_path)
    catalog.initialize()
    bot = MemeBot(settings, catalog)
    bot.run(settings.token, log_handler=None)
