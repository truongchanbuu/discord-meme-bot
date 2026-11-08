# Reuse-first audit (initial)

| Project | Useful pieces | Decision |
| --- | --- | --- |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | Typo-tolerant string scoring (`WRatio`, `process.extractOne`) | **Use as dependency** under its [MIT license](https://github.com/rapidfuzz/RapidFuzz/blob/main/LICENSE). Install `rapidfuzz>=3.14,<4`; keep Vietnamese normalization, scope filtering and ranking rules in the application. No source is copied or vendored. |
| [discord.py](https://github.com/Rapptz/discord.py) | Discord gateway, slash commands, selects, buttons and file resends | **Use as dependency**; no need to write protocol handling |
| [nirowu/discord-image-bot](https://github.com/nirowu/discord-image-bot) | Upload indexing, OCR, fuzzy text search, dropdown patterns (Python) | **Design reference only**: a root LICENSE file wasn't found in the audit. Do not copy source without permission/license clarification. |
| [hberg539/memebase](https://github.com/hberg539/memebase) | Tagging, image management, copying/downloading concepts | MIT-licensed, but its Flask web UI/local file architecture is a poor fit for native Discord only. Avoid importing its web stack. |

This repository implements a small independent Discord adapter and SQLite catalog, not a fork of the other two projects. If a licensed library is found that materially eliminates code, prefer it and record the tradeoff in this document.
