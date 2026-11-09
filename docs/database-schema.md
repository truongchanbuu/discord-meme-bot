# SQLite catalog schema

Discord stores the original attachments. SQLite stores names, search keys, category mappings,
editable tags and Discord identifiers. The schema is defined and migrated in
`src/meme_manager/persistence/schema.py`; no external database is required.

| Table | Key | Purpose |
| --- | --- | --- |
| `meme_settings` | `guild_id` | Saved ID of the bot-managed Memes group (`category_id`) |
| `meme_channels` | `(guild_id, name)` | Requested category name mapped to its Discord text channel ID |
| `memes` | `id`, unique `attachment_id` | One record per original attachment |
| `folder_imports` | `(guild_id, category, content_hash)` | Durable folder-upload checkpoint keyed by canonical category and SHA-256 |

A business category such as `reaction` is a Discord text channel. The enclosing Discord
Category named Memes is the library container. These are different identifiers.

`memes.channel_id` identifies the business category, scoped by `guild_id`. `meme_channels`
remembers requested names so renamed channels can still be reopened by the original command.
Manually added channels may have indexed attachments without a requested-name mapping.
These are logical relationships; they are not enforced with foreign keys because source
channels can be renamed, moved, or deleted independently in Discord.

| Meme field | Meaning |
| --- | --- |
| `id` | Local meme ID shown by the picker and used for edit/remove |
| `title` | Display name; initially derived from the filename, editable |
| `name_index` | Normalized title: lowercase, accent-insensitive, punctuation/spacing normalized |
| `filename` | Original Discord attachment filename |
| `tags` | User-editable tags |
| `message_text` | Original caption, bounded to 1000 characters |
| `search_text` | Normalized title + tags + caption + channel name |
| `guild_id`, `channel_id` | Source server and category channel |
| `channel_name` | Source channel name snapshot, refreshed on reimport |
| `message_id`, `attachment_id` | Stable references used to refetch the original attachment |
| `author_id` | Original author; edit/remove authorization uses this ID |
| `media_kind`, `content_type`, `file_size` | Image/video classification and attachment metadata |

Titles do not need to be unique. `name_index` is a search key, not a second ID or a filename.
For example, `Mèo Hết Cứu!` has the key `meo het cuu`. Creating or editing a meme maintains
this value. Reimport preserves edited names and tags.

| Index | Supports |
| --- | --- |
| Primary key `memes.id` | Get/edit/remove by local meme ID |
| Unique `memes.attachment_id` | Idempotent attachment ingestion |
| `idx_memes_guild_id (guild_id, id DESC)` | Recent memes within the server |
| `idx_memes_guild_name (guild_id, name_index, id DESC)` | Exact normalized name lookup within the server |
| `idx_memes_guild_channel (guild_id, channel_id, id DESC)` | Recent/search results filtered by category |
| `idx_memes_source_message (guild_id, channel_id, message_id)` | Remove attachments when the source message is deleted |
| Primary key `meme_channels (guild_id, name)` | Reopen a category by requested name |
| `idx_meme_channels_discord (guild_id, channel_id)` | Inspect requested category names for a Discord channel |

`/meme search` delegates to `services/search.py`. SQLite first filters the server and optional
category, streaming all matching rows in batches of 200. The service reads `name_index` and
normalizes the other fields, then ranks exact names, name keywords, metadata keywords and
RapidFuzz matches. The result limit applies after ranking; candidates are not restricted to
the latest page. The existing guild/category indexes support this candidate query.

`/meme list` retains the recent-first SQLite query. The repository's literal search method
continues using parameterized `LIKE`; the name B-tree index does not accelerate arbitrary
substring matches. It supports exact-name SQL lookups such as the query below. There is no
FTS table, fuzzy index, persisted score or media-content indexing.

```sql
SELECT id, title, channel_name
FROM memes
WHERE guild_id = :guild_id AND name_index = :normalized_name
ORDER BY id DESC;
```

On startup, existing databases gain missing columns and indexes. Existing titles backfill
`name_index`; attachment IDs, names, tags and managed channel mappings remain intact. Repeated
startup is safe. The old message-only index is replaced by the scoped source-message index.
Back up the SQLite database before upgrades; do not edit derived search keys manually.

## Folder upload checkpoints

`folder_imports` stores `guild_id`, canonical `category`, `content_hash`, source `relative_path`,
`channel_id`, `message_id` and `attachment_id`. The composite primary key is the resume lookup
index. Only relative paths and hashes are stored, with no local media bytes, tokens or CDN URLs.
The table is added automatically on initialization without rewriting existing records.

A successful Discord upload checkpoints its reference before the separate meme-index write.
A rerun can therefore restore the index from that reference without reposting. Removing a meme
from search does not remove its checkpoint; explicitly rerunning the folder import reindexes
it if the original remains accessible. A confirmed deleted attachment can be reuploaded and
replace the checkpoint, removing only its stale index entry. Guild/category boundaries apply
to checkpoint lookups. There is no cross-system transaction or concurrent-import lease.
