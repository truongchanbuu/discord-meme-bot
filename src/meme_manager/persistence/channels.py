"""Persist guild-scoped Discord group IDs and requested category names."""

from meme_manager.persistence.database import SQLiteDatabase


class ChannelRegistry:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_meme_category_id(self, guild_id: int) -> int | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT category_id FROM meme_settings WHERE guild_id = ?", (guild_id,)
            ).fetchone()
        return int(row[0]) if row is not None else None

    def set_meme_category_id(self, guild_id: int, category_id: int) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO meme_settings (guild_id, category_id) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET category_id = excluded.category_id",
                (guild_id, category_id),
            )

    def get_meme_channel_id(self, guild_id: int, name: str) -> int | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT channel_id FROM meme_channels WHERE guild_id = ? AND name = ?",
                (guild_id, name),
            ).fetchone()
        return int(row[0]) if row is not None else None

    def set_meme_channel_id(self, guild_id: int, name: str, channel_id: int) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO meme_channels (guild_id, name, channel_id) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id, name) DO UPDATE SET channel_id = excluded.channel_id",
                (guild_id, name, channel_id),
            )
