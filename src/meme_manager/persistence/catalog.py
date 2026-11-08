"""SQLite queries for meme metadata; media bytes remain in Discord."""

from collections.abc import Iterator
from typing import Any

from meme_manager.domain.media import media_kind
from meme_manager.domain.models import Meme, MemeInput
from meme_manager.domain.text import default_title, normalize
from meme_manager.persistence.database import SQLiteDatabase

SEARCH_BATCH_SIZE = 200

_COLUMNS = (
    "id, guild_id, channel_id, message_id, attachment_id, author_id, "
    "filename, title, tags, message_text, media_kind, content_type, file_size, channel_name, name_index"
)


class MemeCatalog:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def add(self, item: MemeInput) -> bool:
        """Index media or refresh its channel name, preserving edited titles and tags."""
        kind = media_kind(item.filename, item.content_type)
        if kind is None:
            return False
        title = default_title(item.filename)
        message_text = item.message_text[:1000]
        search_text = normalize(f"{title} {message_text} {item.channel_name}")
        with self.database.connection() as connection:
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
        with self.database.connection() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [_as_meme(row) for row in rows]

    def iter_search_candidates(
        self, guild_id: int, *, channel_id: int | None = None
    ) -> Iterator[Meme]:
        """Stream every scoped candidate so ranking never truncates to recent uploads."""
        statement = f"SELECT {_COLUMNS} FROM memes WHERE guild_id = ?"
        parameters = [guild_id]
        if channel_id is not None:
            statement += " AND channel_id = ?"
            parameters.append(channel_id)
        statement += " ORDER BY id DESC"
        with self.database.connection() as connection:
            cursor = connection.execute(statement, parameters)
            while rows := cursor.fetchmany(SEARCH_BATCH_SIZE):
                for row in rows:
                    yield _as_meme(row)

    def random(self, guild_id: int) -> Meme | None:
        """Random selection across the full catalog, not just the last page."""
        with self.database.connection() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM memes WHERE guild_id = ? ORDER BY RANDOM() LIMIT 1",
                (guild_id,),
            ).fetchone()
        return _as_meme(row) if row is not None else None

    def get(self, meme_id: int, guild_id: int) -> Meme | None:
        with self.database.connection() as connection:
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
        with self.database.connection() as connection:
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
        with self.database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memes WHERE id = ? AND guild_id = ?", (meme_id, guild_id)
            )
        return cursor.rowcount > 0

    def remove_message(self, guild_id: int, channel_id: int, message_id: int) -> int:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memes WHERE guild_id = ? AND channel_id = ? AND message_id = ?",
                (guild_id, channel_id, message_id),
            )
        return cursor.rowcount


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
