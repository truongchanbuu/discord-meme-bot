"""Plain value objects. This module must never import discord.py or a database client."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemeInput:
    guild_id: int
    channel_id: int
    message_id: int
    attachment_id: int
    author_id: int
    filename: str
    content_type: str | None
    file_size: int
    message_text: str
    channel_name: str = ""


@dataclass(frozen=True, slots=True)
class Meme:
    id: int
    guild_id: int
    channel_id: int
    message_id: int
    attachment_id: int
    author_id: int
    filename: str
    title: str
    tags: str
    message_text: str
    media_kind: str
    content_type: str | None
    file_size: int
    channel_name: str = ""
    name_index: str = ""

    @property
    def jump_url(self) -> str:
        return f"https://discord.com/channels/{self.guild_id}/{self.channel_id}/{self.message_id}"
