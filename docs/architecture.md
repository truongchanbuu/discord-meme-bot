# Architecture — intentionally small

```text
Discord Server
  Meme category / text channels --message create/delete--> MemeBot.on_message/on_raw_message_delete
                                          |  index references
                                          v
                                     MemeCatalog (SQLite)
                                          ^
  /meme search/list/random/edit/remove ---|
          |
          v
    MemePicker (Select, Buttons, Embed)
          |
    Send to channel -> re-fetch original Discord message attachment -> upload to chat
```

## Boundaries

- `bot.py` handles Discord gateway events, managed group/channel creation and attachment resending. Separate asyncio locks serialize group setup and channel creation within the single bot process.
- `commands.py` registers slash commands, checks editing permissions and restricts category creation/import to server managers in the configured guild.
- `views.py` renders native Discord select menus, preview embeds, and buttons.
- `catalog.py` owns indexing, querying, tag edits, deletion and SQLite schema.
- `models.py`, `text.py`, `media.py` are SDK-agnostic pure data/validation helpers.
- `config.py` loads token, guild ID, and DB path; Discord IDs are managed in SQLite.

No service registry, generic repository framework, DI container, message broker, worker, Redis, or external database. Add components only when a measured requirement demands them.

## Category lifecycle

- On ready, the bot fetches guild channels, restores the group saved in `meme_settings`, or reuses a unique category named `Memes`. Otherwise it creates Memes and saves its ID.
- `/meme category create name:...` normalizes the name, checks `meme_channels`, and reuses or creates a text channel under that group. IDs are saved only after successful Discord operations. Fresh channel lists avoid depending on gateway cache timing after creation.
- Saved IDs survive Discord renames. A deleted resource is recovered on the next setup/create call; ambiguous names and moved children report an error instead of changing unrelated channels.
- `meme_settings` and `meme_channels` are guild-scoped SQLite tables. The schema is created on startup alongside the existing catalog. Token, guild ID and database path are the only environment settings.

## Data invariants

- `memes.title` is the display name; `name_index` is its normalized search key. Edits maintain both. See [database schema](database-schema.md) for fields and indexes.
- Category-filtered list/search uses `channel_id` and always retains the configured guild boundary.
- One row per `attachment_id` (idempotent indexing). Reimport refreshes the searchable channel name and preserves edited titles/tags.
- Only direct text channels in the managed category receive new entries; threads and forums are excluded.
- Channel names are stored as metadata for category search; existing databases migrate on startup.
- Guild-bound queries and mutating commands.
- An attachment is referenced by original `guild_id/channel_id/message_id/attachment_id`.
- A signed CDN URL is **never stored** in SQLite.
- Deleting original message clears indexed rows when the bot sees its deletion event; outages may leave stale records, so a future reconciliation command can clean them.
- Removing an index entry does not delete original messages.
- The current bot does not hash bytes, OCR, transcode media, or search videos by content.

## Decisions and limitations

1. SQLite + `sqlite3`: sufficient for one modest personal bot. Most operations are tiny, synchronous metadata queries; revisit event-loop blocking if usage grows.
2. Discord attachments: lowest setup friction, but **not an archival guarantee**. Retain external backups for anything irreplaceable.
3. Native Discord UI: a select menu of 5 results per page, preview embed, and Send button. Images/GIFs use a fresh attachment URL in the embed. Videos are reattached to the ephemeral response for native Discord playback, within the effective interaction upload limit. Every preview replaces the previous attachments; missing/oversized/download-failed media has a source link. A per-picker lock serializes rendering so slow downloads cannot overwrite newer selections.
4. One guild: prevents accidental cross-server access and simplifies authorization. Multi-server/user-install is a separate feature.
