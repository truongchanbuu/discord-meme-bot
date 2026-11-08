# Discord Meme Manager

A **Discord-native** meme bot written in Python. **No web frontend or dashboard.**

Upload images, GIFs, or short videos to text channels in one Discord category; the bot indexes their metadata in local SQLite. Search, preview, select, and resend a meme using native Discord slash commands, select menus, and buttons. The actual files **stay attached to the original Discord messages**, not in SQLite or another cloud bucket.

## Discord workflow

1. Start the bot; it creates or reuses the **Memes** Discord category. As a server manager, use `/meme category create name:cat` to create the `#cat` meme channel. Repeat with `reaction`, `anime`, or another category name.
2. Upload `cat-crying.gif` to `#cat`, optionally with a description (`mèo khóc`).
3. In any channel in **that server**, use `/meme search query:meo khoc`.
4. Select a result in the dropdown: images/GIFs appear in the preview, and videos are attached to the private result for Discord playback. Click **Send to channel** to share publicly.
5. To paste outside Discord, use the Discord client's native **Copy Image**, **Save**, or **Share** actions on the sent image/GIF/video. These options depend on file type and client. The bot cannot directly modify your device clipboard.

| Command | Purpose |
| --- | --- |
| `/meme category create name:...` | Create or open a meme channel under Memes (Manage Server required) |
| `/meme search query:... category:...` | Search names, captions, tags, and channel names with accent-insensitive ranking and typo tolerance; optionally filter by category channel |
| `/meme list category:...` | Browse recently indexed memes; optionally select a category channel (first 100 results) |
| `/meme random` | Send a random indexed meme |
| `/meme edit meme_id:... title:... tags:...` | Rename or tag a meme (uploader or server manager) |
| `/meme remove meme_id:...` | Unindex a meme, **without deleting the original upload** |
| `/meme import limit:...` | Backfill up to `limit` messages per text channel in the meme category (server manager) |

Supports `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.mp4`, `.webm`, `.mov`; actual playback and upload limits depend on Discord and client support. Search uses Vietnamese text normalization and RapidFuzz: exact names rank first, followed by name keywords, metadata keywords and near matches. No OCR or semantic search is implemented.

## Start the bot

**Requirements:** Python 3.12+, a Discord application/bot token, and a server you control.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
cp .env.example .env            # Windows: copy .env.example .env
```

Open [Discord Developer Portal](https://discord.com/developers/applications), create an application, and create its bot token. Under **Bot → Privileged Gateway Intents**, enable **Message Content Intent** to detect uploaded attachments and captions. Install it in your server with `bot` and `applications.commands` scopes. Grant it **Manage Channels** to create the Memes group and meme channels, plus **View Channel**, **Read Message History**, **Send Messages**, and **Attach Files** in relevant channels. Copy only your server ID via Discord Developer Mode. Channel creation uses the [official discord.py guild API](https://discordpy.readthedocs.io/en/stable/api.html#discord.Guild.create_text_channel).

Set `.env` values:

```dotenv
DISCORD_BOT_TOKEN=replace_me
DISCORD_GUILD_ID=123456789012345678
MEME_DB_PATH=data/memes.sqlite3
```

Run:

```bash
python -m meme_manager
# or: meme-bot
```

Slash commands are registered to the specified guild at startup, so this first version works inside **one server**. The bot must stay running to respond to commands and index new uploads. Run `/meme import limit:200` if files were uploaded before the bot started. This scans up to 200 recent messages in each direct text channel of the managed Memes category. Create more meme channels with `/meme category create name:reaction`; direct text channels manually added to Memes are also indexed. Threads and forum posts are not indexed. Bot-authored messages are ignored, so resending a meme does not duplicate the catalog.

Channel names become searchable categories without replacing editable tags. Existing SQLite databases are upgraded automatically; run import again to add channel names to existing entries while preserving titles and tags. After renaming a channel, reimport its messages to refresh their indexed channel name. Deletion events remove indexed attachments even if the original channel has since moved outside the category. Entries are retained when channels move; removing an entry still uses `/meme remove`.

## Search behavior

`/meme search` uses `MemeSearchService` and [RapidFuzz](https://rapidfuzz.github.io/RapidFuzz/Usage/process.html).
For example, `cat vo tya` can find `cat vo tay`, and `goffy bi` can find `Goofy Bi`.
Names, tags, captions and channel names support case/accent-insensitive matching.

Results prioritize exact names, then name keywords, then metadata keywords, then fuzzy matches.
Within each tier, similarity is ranked first and newer uploads break ties. Every query word must
have a literal or sufficiently similar counterpart; unrelated words are not ignored. Queries
shorter than four non-space characters use literal matches only. Empty/punctuation-only queries
return no results. Up to 12 query words and 100 results are supported.

Server/category filters run in SQLite before ranking. Candidates stream in batches without a
recent-upload cutoff, so an old meme can still be the best match. This scans the selected
collection and keeps only the best requested results in memory; it is intended for a personal
library rather than a large search cluster. Edits, imports and removals take effect immediately.
`/meme list` continues to browse the latest indexed memes. No database migration is needed for
fuzzy search.

## Managed categories

- The bot prepares the **Memes** Discord category when it connects. `/meme category create` also retries setup if it previously failed. No category or channel IDs belong in `.env`.
- The command requires **Manage Server** and replies privately with the channel link. Names are normalized (`Mèo Khóc` becomes `meo-khoc`); empty names and names over 100 characters after normalization are rejected.
- SQLite stores the group ID and each requested category name's channel ID, scoped to the configured server. Restarts and repeat commands reuse the saved channels, including after renaming them in Discord. Run only one bot process with this database.
- If no saved group is available, the bot reuses a single group named exactly **Memes**, or creates one. If migrating an existing meme group, rename it to **Memes** before starting the updated bot. Existing channels and uploads remain intact; run `/meme import` to index them.
- A missing channel is recreated when its create command is used again; a deleted group is recovered on reconnect or the next create/import command. Deleted uploads cannot be restored. If multiple groups/channels share the requested name, rename the duplicates before retrying. A saved child moved outside Memes must be moved back before reusing its original category command.
- New channels inherit the group's Discord permissions. Choose who can view/upload by configuring those permissions in Discord. Missing bot permissions are reported privately by commands and in startup logs; fixing permissions and retrying does not require editing any IDs.
- Back up the SQLite database to preserve the group's identity, category mappings, and edited meme metadata. Existing databases upgrade automatically.

See [the SQLite schema](docs/database-schema.md) for stored fields, category mappings, normalized names, indexes and migration behavior.

## Code organization

- `domain/`: plain records, validation and repository contracts.
- `persistence/`: SQLite connections, migrations and focused repositories.
- `services/`: application rules, including relevance ranking and fuzzy search.
- `discord_app/`: gateway, category/media adapters, picker and commands grouped by task.
- `app.py`: constructs the production dependencies and starts the bot.

See [architecture](docs/architecture.md) for the dependency rules and directory map.
Tests follow the same layers and use isolated SQLite databases without Discord credentials.

## Development

```bash
python -m pip install -e '.[dev]'
ruff format .
ruff check .
mypy src
pytest -q
```

Read [docs/architecture.md](docs/architecture.md) for the architecture, [docs/coding-style.md](docs/coding-style.md) for coding conventions, and [docs/reuse-audit.md](docs/reuse-audit.md) for dependency decisions.

## Intentional limits and tradeoffs

- Discord attachments are **not guaranteed permanent object storage**. If an original upload is deleted, access is revoked, or Discord changes its service, the catalog entry becomes unusable. Back up important media separately.
- Signed attachment URLs expire. The database stores Discord message and attachment IDs, and the bot refetches a message to obtain a fresh URL when previewing or resending.
- Video previews download and reattach the selected video privately; switching results replaces the previous attachment. Oversized or unavailable videos retain a source link. Playback depends on Discord/client codec support.
- Files may need to be downloaded and uploaded again to send into chat; file-size limits and permissions apply. The bot falls back to a source-message link on upload failure.
- SQLite data is local to the bot process; back up `data/memes.sqlite3` if tags and edits matter. For a single bot instance, no managed database is required.
- This is a small, single-server MVP. No full-text engine, AI, OCR, external website, Supabase, or Redis is shipped.
- `discord-image-bot` was evaluated for ideas but **not copied**: no license file was visible in its root. See [reuse audit](docs/reuse-audit.md).
