"""Measure current search latency against disposable synthetic SQLite catalogs."""

import argparse
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from meme_manager.config import RuntimeConfig
from meme_manager.domain.text import normalize
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.database import SQLiteDatabase
from meme_manager.services.search import MemeSearchService

QUERIES = ("cat vo tay", "votay", "votya", "zxqv blrp", "reactoin")


def seed_database(database: SQLiteDatabase, size: int) -> None:
    database.initialize()
    rows = []
    for number in range(1, size + 1):
        title = "Cat vỗ tay" if number == 1 else f"unrelated folder item {number}"
        caption = "hello random gaming collection"
        rows.append(
            (
                number,
                1,
                2,
                number,
                number,
                50,
                f"{number}.gif",
                title,
                normalize(title),
                "",
                caption,
                normalize(f"{title} {caption} reaction"),
                "image",
                "image/gif",
                "reaction",
                100,
            )
        )
    with database.connection() as connection:
        connection.executemany(
            "INSERT INTO memes (id,guild_id,channel_id,message_id,attachment_id,author_id,"
            "filename,title,name_index,tags,message_text,search_text,media_kind,content_type,"
            "channel_name,file_size) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )


def benchmark(size: int, repeats: int, path: Path) -> None:
    config = RuntimeConfig.load()
    database = SQLiteDatabase(path, config.database)
    seed_database(database, size)
    search = MemeSearchService(MemeCatalog(database, config.media, config.search), config.search)
    for query in QUERIES:
        search.search(1, query, limit=5)
        durations = []
        for _ in range(repeats):
            start = perf_counter()
            results = search.search(1, query, limit=5)
            durations.append((perf_counter() - start) * 1000)
        top = results[0].title if results else "(none)"
        print(f"{size:>6} rows | {query:<12} | median {median(durations):>8.2f} ms | {top}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 5000])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1 or any(size < 1 for size in args.sizes):
        parser.error("sizes and repeats must be positive")
    with TemporaryDirectory(prefix="meme-search-benchmark-") as temporary:
        for index, size in enumerate(args.sizes):
            benchmark(size, args.repeats, Path(temporary) / f"catalog-{index}.sqlite3")


if __name__ == "__main__":
    main()
