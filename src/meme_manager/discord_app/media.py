"""Fetch original Discord attachments and resend selected media."""

import logging

import discord

from meme_manager.domain.models import Meme

LOG = logging.getLogger(__name__)


class MemeMedia:
    def __init__(self, client: discord.Client) -> None:
        self.client = client

    async def get_attachment(self, meme: Meme) -> discord.Attachment | None:
        """Fetch a fresh attachment URL instead of persisting an expiring CDN link."""
        try:
            channel = self.client.get_channel(meme.channel_id) or await self.client.fetch_channel(
                meme.channel_id
            )
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
