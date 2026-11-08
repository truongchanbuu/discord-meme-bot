"""Application entrypoint and composition root for production dependencies."""

import logging

from meme_manager.config import Settings
from meme_manager.discord_app.bot import MemeBot
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.channels import ChannelRegistry
from meme_manager.persistence.database import SQLiteDatabase


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_environment()
    database = SQLiteDatabase(settings.database_path)
    database.initialize()
    bot = MemeBot(settings, MemeCatalog(database), ChannelRegistry(database))
    bot.run(settings.token, log_handler=None)
