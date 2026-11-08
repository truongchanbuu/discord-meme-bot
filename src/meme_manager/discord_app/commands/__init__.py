"""Assemble the single guild's slash command group."""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord import app_commands

from meme_manager.discord_app.commands.browse import register_browse_commands
from meme_manager.discord_app.commands.categories import register_category_commands
from meme_manager.discord_app.commands.manage import register_manage_commands

if TYPE_CHECKING:
    from meme_manager.discord_app.bot import MemeBot


def register_commands(bot: MemeBot) -> None:
    group = app_commands.Group(name="meme", description="Search and share saved memes")
    register_browse_commands(group, bot)
    register_category_commands(group, bot)
    register_manage_commands(group, bot)
    bot.tree.add_command(group, guild=bot.guild)
