"""Database ownership must commit, roll back and release connections reliably."""

import sqlite3

import pytest

from meme_manager.persistence.database import SQLiteDatabase


def test_commits_successful_transaction_and_closes_connection(database: SQLiteDatabase) -> None:
    with database.connection() as connection:
        connection.execute("INSERT INTO meme_settings VALUES (1, 20)")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with database.connection() as reopened:
        assert reopened.execute("SELECT category_id FROM meme_settings").fetchone() == (20,)


def test_rolls_back_failed_transaction_and_closes_connection(database: SQLiteDatabase) -> None:
    with pytest.raises(ValueError, match="abort"), database.connection() as connection:
        connection.execute("INSERT INTO meme_settings VALUES (1, 20)")
        raise ValueError("abort")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with database.connection() as reopened:
        assert reopened.execute("SELECT * FROM meme_settings").fetchall() == []
