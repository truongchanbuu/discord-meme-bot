"""CLI for local folder planning, Discord uploads and SQLite indexing."""

import argparse
import asyncio
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

import discord

from meme_manager.config import Settings
from meme_manager.discord_app.categories import CategoryManager
from meme_manager.discord_app.folder_upload import DiscordFolderUploader
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.channels import ChannelRegistry
from meme_manager.persistence.database import SQLiteDatabase
from meme_manager.persistence.imports import FolderImportStore
from meme_manager.services.folder_import import FolderImportService, FolderPlan, scan_folder


def report(message: str) -> None:
    print(message, flush=True)


async def upload_plan(settings: Settings, plan: FolderPlan) -> int:
    database = SQLiteDatabase(settings.database_path)
    database.initialize()
    async with discord.Client(intents=discord.Intents.none()) as client:
        # Login supplies REST access only: do not sync commands or connect another gateway.
        await client.login(settings.token)
        guild = await client.fetch_guild(settings.guild_id)
        categories = CategoryManager(settings.guild_id, ChannelRegistry(database))
        uploader = DiscordFolderUploader(client, guild, categories)
        service = FolderImportService(
            settings.guild_id, MemeCatalog(database), FolderImportStore(database), uploader, report
        )
        summary = await service.run(plan.files)
    report(
        f"Hoàn tất: upload={summary.uploaded}, index={summary.indexed}, "
        f"bỏ qua={summary.skipped + plan.skipped}, lỗi={summary.failed + len(plan.errors)}"
    )
    return 1 if summary.failed or plan.errors else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upload meme từ folder vào Discord và lập danh mục."
    )
    parser.add_argument("folder", type=Path, help="Folder nguồn; thư mục con cấp đầu là category")
    parser.add_argument("--category", help="Dùng một category cho toàn bộ file trong folder")
    parser.add_argument(
        "--dry-run", action="store_true", help="Chỉ quét file, không kết nối Discord/ghi DB"
    )
    args = parser.parse_args(argv)
    try:
        plan = scan_folder(args.folder, args.category)
    except (OSError, ValueError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 2
    for issue in plan.errors:
        report(f"ERROR {issue}")
    report(
        f"Đã quét: {len(plan.files)} file hợp lệ, {plan.skipped} file bỏ qua, {len(plan.errors)} lỗi"
    )
    if args.dry_run:
        for source in plan.files:
            report(f"PLAN #{source.category}: {source.relative_path} ({source.file_size} bytes)")
        return 1 if plan.errors else 0
    if not plan.files:
        return 1 if plan.errors else 0
    try:
        return asyncio.run(upload_plan(Settings.from_environment(), plan))
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1
    except discord.HTTPException as error:
        print(f"ERROR Discord HTTP {error.status}, code {error.code}", file=sys.stderr)
        return 1
    except discord.LoginFailure:
        print("ERROR Token bot không hợp lệ; kiểm tra DISCORD_BOT_TOKEN.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "Đã dừng import. Các upload đã checkpoint sẽ được bỏ qua khi chạy lại.", file=sys.stderr
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
