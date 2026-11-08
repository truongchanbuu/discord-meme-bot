"""SQLite metadata catalog. Media bytes stay in their original Discord messages."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from meme_manager.media import media_kind
from meme_manager.models import Meme, MemeInput
from meme_manager.text import default_title, normalize

_COLUMNS = (
    "id, guild_id, channel_id, message_id, attachment_id, author_id, "
    "filename, title, tags, message_text, media_kind, content_type, file_size, channel_name, name_index"
)


class MemeCatalog:
    """Index attachments by Discord ID, never by a temporary CDN URL."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
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
                connection.execute(
                    "ALTER TABLE memes ADD COLUMN channel_name TEXT NOT NULL DEFAULT ''"
                )
            if "name_index" not in columns:
                connection.execute(
                    "ALTER TABLE memes ADD COLUMN name_index TEXT NOT NULL DEFAULT ''"
                )
            rows = connection.execute(
                "SELECT id, title FROM memes WHERE name_index = ''"
            ).fetchall()
            connection.executemany(
                "UPDATE memes SET name_index = ? WHERE id = ?",
                [(normalize(title), meme_id) for meme_id, title in rows],
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memes_guild_name "
                "ON memes(guild_id, name_index, id DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memes_guild_channel "
                "ON memes(guild_id, channel_id, id DESC)"
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

    def get_meme_category_id(self, guild_id: int) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT category_id FROM meme_settings WHERE guild_id = ?", (guild_id,)
            ).fetchone()
        return int(row[0]) if row is not None else None

    def set_meme_category_id(self, guild_id: int, category_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO meme_settings (guild_id, category_id) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET category_id = excluded.category_id",
                (guild_id, category_id),
            )

    def get_meme_channel_id(self, guild_id: int, name: str) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT channel_id FROM meme_channels WHERE guild_id = ? AND name = ?",
                (guild_id, name),
            ).fetchone()
        return int(row[0]) if row is not None else None

    def set_meme_channel_id(self, guild_id: int, name: str, channel_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO meme_channels (guild_id, name, channel_id) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id, name) DO UPDATE SET channel_id = excluded.channel_id",
                (guild_id, name, channel_id),
            )

    def add(self, item: MemeInput) -> bool:
        """Index media or refresh its channel name, preserving edited titles and tags."""
        kind = media_kind(item.filename, item.content_type)
        if kind is None:
            return False
        title = default_title(item.filename)
        message_text = item.message_text[:1000]
        search_text = normalize(f"{title} {message_text} {item.channel_name}")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO memes (
                    guild_id, channel_id, message_id, attachment_id, author_id,
                    filename, title, tags, message_text, search_text,
                    media_kind, content_type, file_size, channel_name, name_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.guild_id,
                    item.channel_id,
                    item.message_id,
                    item.attachment_id,
                    item.author_id,
                    item.filename,
                    title,
                    message_text,
                    search_text,
                    kind,
                    item.content_type,
                    item.file_size,
                    item.channel_name,
                    normalize(title),
                ),
            )
            if cursor.rowcount == 0:
                existing = connection.execute(
                    "SELECT title, tags, message_text FROM memes "
                    "WHERE attachment_id = ? AND guild_id = ? AND channel_id = ?",
                    (item.attachment_id, item.guild_id, item.channel_id),
                ).fetchone()
                if existing is not None:
                    search_text = normalize(f"{' '.join(existing)} {item.channel_name}")
                    connection.execute(
                        "UPDATE memes SET channel_name = ?, search_text = ? "
                        "WHERE attachment_id = ? AND guild_id = ? AND channel_id = ?",
                        (
                            item.channel_name,
                            search_text,
                            item.attachment_id,
                            item.guild_id,
                            item.channel_id,
                        ),
                    )
        return cursor.rowcount > 0

    def search(
        self, guild_id: int, query: str = "", limit: int = 100, *, channel_id: int | None = None
    ) -> list[Meme]:
        """Match each search word; LIKE wildcards in user input are escaped."""
        words = normalize(query).split()[:12]
        if query.strip() and not words:
            return []
        filters = ["guild_id = ?"]
        parameters: list[str | int] = [guild_id]
        if channel_id is not None:
            filters.append("channel_id = ?")
            parameters.append(channel_id)
        for word in words:
            filters.append("search_text LIKE ? ESCAPE '\\'")
            escaped_word = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.append(f"%{escaped_word}%")
        statement = (
            f"SELECT {_COLUMNS} FROM memes WHERE {' AND '.join(filters)} ORDER BY id DESC LIMIT ?"
        )
        parameters.append(min(max(limit, 1), 100))
        with self._connect() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [_as_meme(row) for row in rows]

    def random(self, guild_id: int) -> Meme | None:
        """Random selection across the full catalog, not just the last page."""
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM memes WHERE guild_id = ? ORDER BY RANDOM() LIMIT 1",
                (guild_id,),
            ).fetchone()
        return _as_meme(row) if row is not None else None

    def get(self, meme_id: int, guild_id: int) -> Meme | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM memes WHERE id = ? AND guild_id = ?",
                (meme_id, guild_id),
            ).fetchone()
        return _as_meme(row) if row is not None else None

    def update(self, meme_id: int, guild_id: int, title: str, tags: str) -> bool:
        existing = self.get(meme_id, guild_id)
        if existing is None:
            return False
        clean_title = title.strip()[:120]
        clean_tags = tags.strip()[:300]
        if not clean_title:
            raise ValueError("Meme title cannot be empty")
        with self._connect() as connection:
            search_text = normalize(
                f"{clean_title} {clean_tags} {existing.message_text} {existing.channel_name}"
            )
            cursor = connection.execute(
                "UPDATE memes SET title = ?, name_index = ?, tags = ?, search_text = ? "
                "WHERE id = ? AND guild_id = ?",
                (clean_title, normalize(clean_title), clean_tags, search_text, meme_id, guild_id),
            )
        return cursor.rowcount > 0

    def remove(self, meme_id: int, guild_id: int) -> bool:
        """Remove only the database entry, not the original Discord message."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memes WHERE id = ? AND guild_id = ?", (meme_id, guild_id)
            )
        return cursor.rowcount > 0

    def remove_message(self, guild_id: int, channel_id: int, message_id: int) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM memes WHERE guild_id = ? AND channel_id = ? AND message_id = ?",
                (guild_id, channel_id, message_id),
            )
        return cursor.rowcount

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=10)


def _as_meme(row: tuple[Any, ...]) -> Meme:
    return Meme(
        id=int(row[0]),
        guild_id=int(row[1]),
        channel_id=int(row[2]),
        message_id=int(row[3]),
        attachment_id=int(row[4]),
        author_id=int(row[5]),
        filename=str(row[6]),
        title=str(row[7]),
        tags=str(row[8]),
        message_text=str(row[9]),
        media_kind=str(row[10]),
        content_type=str(row[11]) if row[11] is not None else None,
        file_size=int(row[12]),
        channel_name=str(row[13]),
        name_index=str(row[14]),
    )
