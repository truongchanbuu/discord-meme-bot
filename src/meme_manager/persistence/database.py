"""Own SQLite connections, transaction boundaries and schema initialization."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from meme_manager.domain.options import DatabaseOptions
from meme_manager.persistence.schema import initialize_schema


class SQLiteDatabase:
    def __init__(self, path: Path, options: DatabaseOptions) -> None:
        self.path = path
        self.options = options

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            initialize_schema(connection)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=self.options.timeout_seconds)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
