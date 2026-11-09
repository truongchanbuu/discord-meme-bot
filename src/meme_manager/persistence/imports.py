"""Checkpoint successful folder uploads independently from the searchable index."""

from meme_manager.domain.models import ImportedFile, LocalMeme, MemeInput
from meme_manager.persistence.database import SQLiteDatabase


class FolderImportStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get(self, guild_id: int, category: str, content_hash: str) -> ImportedFile | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT guild_id, channel_id, message_id, attachment_id FROM folder_imports "
                "WHERE guild_id = ? AND category = ? AND content_hash = ?",
                (guild_id, category, content_hash),
            ).fetchone()
        return ImportedFile(*row) if row is not None else None

    def save(self, source: LocalMeme, record: MemeInput) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO folder_imports (guild_id, category, content_hash, relative_path, "
                "channel_id, message_id, attachment_id) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(guild_id, category, content_hash) DO UPDATE SET "
                "relative_path = excluded.relative_path, channel_id = excluded.channel_id, "
                "message_id = excluded.message_id, attachment_id = excluded.attachment_id",
                (
                    record.guild_id,
                    source.category,
                    source.content_hash,
                    source.relative_path,
                    record.channel_id,
                    record.message_id,
                    record.attachment_id,
                ),
            )
