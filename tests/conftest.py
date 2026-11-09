"""Each test receives an isolated database and production repository wiring."""

from pathlib import Path

import pytest

from meme_manager.config import RuntimeConfig, Settings
from meme_manager.discord_app.bot import MemeBot
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.channels import ChannelRegistry
from meme_manager.persistence.database import SQLiteDatabase
from meme_manager.services.search import MemeSearchService


@pytest.fixture
def database(tmp_path: Path, config: RuntimeConfig) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "nested" / "catalog.sqlite3", options=config.database)
    database.initialize()
    return database


@pytest.fixture
def catalog(database: SQLiteDatabase, config: RuntimeConfig) -> MemeCatalog:
    return MemeCatalog(database, media=config.media, search=config.search)


@pytest.fixture
def channels(database: SQLiteDatabase) -> ChannelRegistry:
    return ChannelRegistry(database)


@pytest.fixture
def bot(
    database: SQLiteDatabase, catalog: MemeCatalog, channels: ChannelRegistry, config: RuntimeConfig
) -> MemeBot:
    return MemeBot(
        Settings("test-token", 1, database.path, config=config),
        catalog,
        channels,
        MemeSearchService(catalog, options=config.search),
    )


@pytest.fixture
def config() -> RuntimeConfig:
    return RuntimeConfig.load()
