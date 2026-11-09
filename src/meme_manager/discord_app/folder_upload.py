"""REST-only folder uploads; never connect a second Discord gateway session."""

from hashlib import file_digest, sha256

import discord

from meme_manager.discord_app.categories import CategoryManager
from meme_manager.domain.models import ImportedFile, LocalMeme, Meme, MemeInput
from meme_manager.services.folder_import import UploadError


class DiscordFolderUploader:
    def __init__(
        self, client: discord.Client, guild: discord.Guild, categories: CategoryManager
    ) -> None:
        self.client = client
        self.guild = guild
        self.categories = categories
        self._channels: dict[str, discord.TextChannel] = {}

    async def upload(self, source: LocalMeme) -> MemeInput:
        if source.file_size > self.guild.filesize_limit:
            raise UploadError("File vượt giới hạn upload của server")
        file = discord.File(source.path)
        try:
            if file_digest(file.fp, "sha256").hexdigest() != source.content_hash:
                raise UploadError("File đã thay đổi sau khi quét; hãy chạy lại CLI")
            file.fp.seek(0)
            channel = self._channels.get(source.category)
            if channel is None:
                channel = await self.categories.create_channel(self.guild, source.category)
                self._channels[source.category] = channel
            message = await channel.send(file=file, allowed_mentions=discord.AllowedMentions.none())
            if not message.attachments:
                raise UploadError("Discord không trả về attachment cho file vừa gửi")
            return self._record(message, message.attachments[0], channel)
        except discord.HTTPException as error:
            raise UploadError(f"Discord HTTP {error.status}, code {error.code}") from error
        finally:
            file.close()

    async def recover(self, reference: ImportedFile) -> MemeInput | None:
        found = await self._fetch_attachment(reference)
        return self._record(*found) if found else None

    async def match_existing(self, source: LocalMeme, candidate: Meme) -> MemeInput | None:
        reference = ImportedFile(
            candidate.guild_id, candidate.channel_id, candidate.message_id, candidate.attachment_id
        )
        found = await self._fetch_attachment(reference)
        if found is None:
            return None
        message, attachment, channel = found
        if attachment.size != source.file_size:
            return None
        try:
            content = await attachment.read()
        except discord.HTTPException as error:
            raise UploadError(
                f"Không đối chiếu được file gốc: Discord HTTP {error.status}"
            ) from error
        if sha256(content).hexdigest() != source.content_hash:
            return None
        return self._record(message, attachment, channel)

    async def _fetch_attachment(
        self, reference: ImportedFile
    ) -> tuple[discord.Message, discord.Attachment, discord.TextChannel] | None:
        if reference.guild_id != self.guild.id:
            raise UploadError("Bản ghi import thuộc server khác")
        try:
            channel = await self.client.fetch_channel(reference.channel_id)
            if not isinstance(channel, discord.TextChannel) or channel.guild.id != self.guild.id:
                raise UploadError("Kênh import không phải kênh text trong server cấu hình")
            group_id = self.categories.registry.get_meme_category_id(self.guild.id)
            if group_id is None or channel.category_id != group_id:
                raise UploadError("Kênh đã chuyển ra ngoài Memes; hãy chuyển lại trước khi import")
            message = await channel.fetch_message(reference.message_id)
        except discord.NotFound:
            return None
        except discord.HTTPException as error:
            raise UploadError(
                f"Không đọc được file gốc: Discord HTTP {error.status}, code {error.code}"
            ) from error
        attachment = next(
            (item for item in message.attachments if item.id == reference.attachment_id), None
        )
        return (message, attachment, channel) if attachment else None

    def _record(
        self, message: discord.Message, attachment: discord.Attachment, channel: discord.TextChannel
    ) -> MemeInput:
        return MemeInput(
            guild_id=self.guild.id,
            channel_id=channel.id,
            message_id=message.id,
            attachment_id=attachment.id,
            author_id=message.author.id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            file_size=attachment.size,
            message_text=message.content,
            channel_name=channel.name,
        )
