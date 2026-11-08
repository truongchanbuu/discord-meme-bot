"""Application entrypoint and composition root for production dependencies."""

import logging

from meme_manager.config import Settings
from meme_manager.discord_app.bot import MemeBot
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.channels import ChannelRegistry
from meme_manager.persistence.database import SQLiteDatabase
from meme_manager.services.search import MemeSearchService


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_environment()
    database = SQLiteDatabase(settings.database_path)
    database.initialize()
    catalog = MemeCatalog(database)
    bot = MemeBot(settings, catalog, ChannelRegistry(database), MemeSearchService(catalog))
    bot.run(settings.token, log_handler=None)
