"""Own SQLite connections, transaction boundaries and schema initialization."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from meme_manager.persistence.schema import initialize_schema

SQLITE_TIMEOUT_SECONDS = 10


class SQLiteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            initialize_schema(connection)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=SQLITE_TIMEOUT_SECONDS)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
