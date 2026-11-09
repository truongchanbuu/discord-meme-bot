# Architecture

One Python bot serves one Discord server. Original uploads stay in Discord; SQLite stores
metadata and stable source identifiers. All user interaction uses native slash commands,
private previews, selects and buttons.

```text
src/meme_manager/
├── app.py                      # Startup and production dependency wiring
├── config.py                   # Typed YAML validation and environment-backed credentials
├── import_folder.py            # CLI composition and dry-run entrypoint
├── domain/
│   ├── options.py              # Typed runtime options without I/O
│   ├── models.py               # Plain meme input/result records
│   ├── text.py                 # Name normalization and search text rules
│   ├── media.py                # Supported media validation
│   └── repositories.py         # Separate meme/channel storage protocols
├── persistence/
│   ├── database.py             # Connections, transactions and initialization
│   ├── schema.py               # SQLite schema and additive migrations
│   ├── catalog.py              # Meme queries, edits and indexing
│   ├── channels.py             # Managed group/channel mappings
│   └── imports.py              # Folder upload checkpoints
├── services/
│   ├── config.py                # Named YAML mapping loader
│   ├── search.py                # Exact/keyword/fuzzy relevance ranking
│   └── folder_import.py         # Local scan, deduplication, resume and indexing
└── discord_app/
    ├── bot.py                  # Gateway events and command synchronization
    ├── categories.py           # Create/recover the Memes group and channels
    ├── media.py                # Retrieve and resend original attachments
    ├── folder_upload.py        # REST-only folder upload/recovery adapter
    ├── picker.py               # Private media preview and result navigation
    └── commands/
        ├── __init__.py         # Assemble the guild's command group
        ├── browse.py           # Search, list and random
        ├── categories.py       # Create categories and import history
        ├── manage.py           # Edit tags/names and remove catalog entries
        └── permissions.py     # Author/server-manager authorization
```

Tests mirror these responsibilities under `tests/domain`, `tests/persistence`, `tests/services`
and `tests/discord_app`; `tests/conftest.py` supplies isolated databases and repository wiring.

```mermaid
flowchart LR
    App[app.py] --> Bot[Discord gateway]
    App --> SQL[SQLite repositories]
    Bot --> Commands[Slash commands]
    Commands --> Picker[Private picker]
    Commands --> Categories[Category manager]
    Picker --> Media[Discord media adapter]
    Bot --> Contracts[Domain repository protocols]
    Commands --> Search[Search service]
    Search --> Contracts
    Categories --> Contracts
    SQL -. implements .-> Contracts
    SQL --> DB[(SQLite metadata)]
    Media --> Discord[(Discord attachments)]
```

## Responsibility and dependency rules

- Domain records, validation and protocols import neither Discord nor SQLite.
- `MemeRepository` and `ChannelRepository` are separate, small typed contracts. Gateway and
  category logic receive those contracts; SQLite implementations are selected in `app.py`.
- `MemeSearchService` depends on the meme repository contract and RapidFuzz, with no Discord
  or SQLite imports. The composition root injects it into the bot for search commands.
  [Search research](search-research.md) documents dual Unicode keys, bounded edit matching,
  normalization-only caching and measured quality/performance.
- Repositories contain SQL only. They share a database object that commits successful work,
  rolls back exceptions and closes every owned connection. Schema migration has its own module.
- `MemeBot` owns gateway behavior. `CategoryManager` owns Discord channel lifecycle; `MemeMedia`
  owns attachment retrieval and sending. The picker depends on media operations, not the bot.
- Command registration is grouped by user task. Shared authorization remains in one module.
- Composition replaces application inheritance; only Discord SDK extension points are subclassed.
  There is no DI container, generic base repository, plugin framework or web backend.

## Category lifecycle

On ready, the bot fetches guild channels and restores the group saved in `meme_settings`.
If necessary, it reuses a unique category named **Memes** or creates one and saves its ID.
`/meme category create name:...` normalizes the requested name, checks `meme_channels`, then
reuses or creates a text channel under that group. Separate locks serialize group setup and
channel creation inside the single bot process. Fresh channel lists avoid relying on gateway
cache timing after creation. IDs are saved only after successful Discord operations.

Saved IDs survive Discord renames. Deleted resources are recovered on the next setup/create
call. Ambiguous names and moved children return an error without moving unrelated channels.
Only direct text channels under Memes receive new entries; threads, forums, bot-authored
messages, DMs and other guilds are excluded. Import requires Manage Server.

## Catalog and privacy invariants

- One row per attachment ID; reimport refreshes the channel name and preserves edited titles/tags.
- Display names and normalized `name_index` values are maintained together. Category-filtered
  search/list always retain the configured guild boundary. See [database schema](database-schema.md).
- Original guild/channel/message/attachment IDs identify media. Signed CDN URLs are refreshed
  from Discord and are never persisted in SQLite. No media bytes are stored in the database.
- Deletion events remove the source's indexed rows, even after its channel moves. Offline
  deletions can leave stale records, which show a missing-media warning when accessed.
- Removing an index entry does not delete the original Discord message.

## Folder import

`python -m meme_manager.import_folder` plans files locally, then uses `FolderImportService`
with repository contracts and a `FolderUploader` protocol. The Discord adapter creates/reuses
category channels and posts files through a plain REST client. It never connects a gateway or
synchronizes slash commands. The main bot intentionally ignores bot-authored messages, so the
CLI indexes returned attachment metadata explicitly. Dry-run creates neither a client nor a DB.

Local SHA-256 keys deduplicate within a server/category. Existing indexed files can be adopted
after remote content verification. Checkpoints commit before catalog writes so reruns can
repair indexing failures. Only a confirmed missing source permits reupload; permissions/errors
do not. Run one importer at a time; acceptance by Discord before a failed local checkpoint is
an unavoidable recovery window. User-facing diagnostics include the uploaded message link.

## Interaction acknowledgement

Search/list commands defer a private response before querying or ranking. Their synchronous
SQLite/search work runs in a worker thread so scans do not block the gateway event loop.
Both empty results and media previews edit that deferred response; the picker never sends a
second initial acknowledgement. This respects Discord's [initial response deadline](https://docs.discord.com/developers/interactions/receiving-and-responding).

## Preview and sharing

Five results appear per page. Images/GIFs use freshly fetched URLs in the preview embed.
Videos are attached to the private response, within the effective interaction upload limit,
for native Discord playback. Selection changes replace previous attachments. A per-picker
lock serializes rendering so a slow download cannot overwrite a newer selection.
Unavailable/oversized media keeps a source link. Only **Send to channel** shares media publicly.
Playback depends on Discord/client codec support.

## Operational limits

Run one bot process per SQLite database and token. Stop the previous terminal process before
starting another; do not leave a background copy running. Repositories remain synchronous;
search/list run their queries in worker threads. Indexing writes are small gateway operations. Discord attachments are not
an archival guarantee: retain backups of important files and the metadata database.
Folder imports use SHA-256 for exact-byte deduplication. No perceptual image matching, OCR,
transcoding or semantic search is implemented. Multiple servers would require
a separate product decision and authorization review.

## Runtime configuration

The composition roots load `config/*.yaml` through `ConfigService` and validate typed
options before creating adapters. Pure media rules receive a shared `MediaPolicy` so folder
scanning and gateway ingestion agree. Search/list resolve a file-type group to extensions
and filter scoped SQLite candidates before ranking. Disabling ingest does not hide existing
records. See [configuration reference](configuration.md). Fixed Discord API limits remain
validation constraints, separate from operational tuning.
