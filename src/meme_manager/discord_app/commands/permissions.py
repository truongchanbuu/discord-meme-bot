"""Shared Discord command authorization rules."""

import discord

from meme_manager.domain.models import Meme


def is_manager(interaction: discord.Interaction) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions is not None and permissions.manage_guild)


def can_manage(interaction: discord.Interaction, meme: Meme) -> bool:
    return interaction.user.id == meme.author_id or is_manager(interaction)
