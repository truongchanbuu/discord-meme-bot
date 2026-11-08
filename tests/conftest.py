"""Each test receives an isolated database and production repository wiring."""

from pathlib import Path

import pytest

from meme_manager.config import Settings
from meme_manager.discord_app.bot import MemeBot
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.channels import ChannelRegistry
from meme_manager.persistence.database import SQLiteDatabase
from meme_manager.services.search import MemeSearchService


@pytest.fixture
def database(tmp_path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "nested" / "catalog.sqlite3")
    database.initialize()
    return database


@pytest.fixture
def catalog(database: SQLiteDatabase) -> MemeCatalog:
    return MemeCatalog(database)


@pytest.fixture
def channels(database: SQLiteDatabase) -> ChannelRegistry:
    return ChannelRegistry(database)


@pytest.fixture
def bot(database: SQLiteDatabase, catalog: MemeCatalog, channels: ChannelRegistry) -> MemeBot:
    return MemeBot(
        Settings("test-token", 1, database.path), catalog, channels, MemeSearchService(catalog)
    )
