"""Discord gateway adapter: sync commands and index attachment lifecycle events."""

import logging

import discord
from discord import app_commands

from meme_manager.config import Settings
from meme_manager.discord_app.categories import CategoryManager
from meme_manager.discord_app.commands import register_commands
from meme_manager.discord_app.media import MemeMedia
from meme_manager.domain.models import MemeInput
from meme_manager.domain.repositories import ChannelRepository, MemeRepository

LOG = logging.getLogger(__name__)


class MemeBot(discord.Client):
    def __init__(
        self, settings: Settings, catalog: MemeRepository, channels: ChannelRepository
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read uploaded attachments and captions.
        super().__init__(intents=intents)
        self.settings = settings
        self.catalog = catalog
        self.channels = channels
        self.categories = CategoryManager(settings.guild_id, channels)
        self.media = MemeMedia(self)
        self.tree = app_commands.CommandTree(self)
        self.guild = discord.Object(id=settings.guild_id)
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
            await self.categories.ensure_group(guild)
        except (discord.HTTPException, ValueError):
            LOG.exception(
                "Could not prepare Memes category; check Manage Channels and View Channel"
            )

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
        category_id = self.channels.get_meme_category_id(self.settings.guild_id)
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
