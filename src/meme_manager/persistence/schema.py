"""Additive SQLite schema migrations preserving existing catalog data."""

import sqlite3

from meme_manager.domain.text import normalize


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS meme_settings (
            guild_id INTEGER PRIMARY KEY,
            category_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meme_channels (
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, name)
        );
        CREATE TABLE IF NOT EXISTS memes (
            id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            attachment_id INTEGER NOT NULL UNIQUE,
            author_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            title TEXT NOT NULL,
            name_index TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            message_text TEXT NOT NULL DEFAULT '',
            search_text TEXT NOT NULL,
            media_kind TEXT NOT NULL,
            content_type TEXT,
            channel_name TEXT NOT NULL DEFAULT '',
            file_size INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memes_guild_id
            ON memes(guild_id, id DESC);
        """
    )

    columns = {row[1] for row in connection.execute("PRAGMA table_info(memes)")}
    if "channel_name" not in columns:
        connection.execute("ALTER TABLE memes ADD COLUMN channel_name TEXT NOT NULL DEFAULT ''")
    if "name_index" not in columns:
        connection.execute("ALTER TABLE memes ADD COLUMN name_index TEXT NOT NULL DEFAULT ''")
    rows = connection.execute("SELECT id, title FROM memes WHERE name_index = ''").fetchall()
    connection.executemany(
        "UPDATE memes SET name_index = ? WHERE id = ?",
        [(normalize(title), meme_id) for meme_id, title in rows],
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_memes_guild_name ON memes(guild_id, name_index, id DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_memes_guild_channel ON memes(guild_id, channel_id, id DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_memes_source_message "
        "ON memes(guild_id, channel_id, message_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_meme_channels_discord "
        "ON meme_channels(guild_id, channel_id)"
    )
    connection.execute("DROP INDEX IF EXISTS idx_memes_message_id")
