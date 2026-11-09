"""Application entrypoint and composition root for production dependencies."""

import logging

from meme_manager.config import Settings
from meme_manager.discord_app.bot import MemeBot
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.channels import ChannelRegistry
from meme_manager.persistence.database import SQLiteDatabase
from meme_manager.services.search import MemeSearchService


def main() -> None:
    settings = Settings.from_environment()
    logging.basicConfig(level=settings.config.bot.log_level, format=settings.config.bot.log_format)
    database = SQLiteDatabase(settings.database_path, settings.config.database)
    database.initialize()
    catalog = MemeCatalog(database, settings.config.media, settings.config.search)
    bot = MemeBot(
        settings,
        catalog,
        ChannelRegistry(database),
        MemeSearchService(catalog, settings.config.search),
    )
    bot.run(settings.token, log_handler=None)
