# Vietnamese meme search: research and implementation

Research date: 2026-11-09. The goal is reliable name/tag lookup for one Discord server,
including Vietnamese accents, filenames, joined words and small typing mistakes.

## Options evaluated

| Option | Evidence and fit | Decision |
| --- | --- | --- |
| Python `unicodedata` | Provides canonical/compatibility normalization; needed to make composed and combining-mark spellings comparable. [Official reference](https://docs.python.org/3.14/library/unicodedata.html) | Use NFKC for search keys, retain accented and folded forms. Display text stays unchanged. |
| RapidFuzz | Provides weighted string scores and Damerau–Levenshtein distance with edit cutoffs. [Distance API](https://rapidfuzz.github.io/RapidFuzz/Usage/distance/DamerauLevenshtein.html), [matching API](https://rapidfuzz.github.io/RapidFuzz/Usage/process.html), [MIT license](https://github.com/rapidfuzz/RapidFuzz/blob/main/LICENSE) | Reuse the installed dependency. Use bounded edit distance to handle insertions, deletions, substitutions and transpositions. |
| SQLite FTS5 | Supports full-text/prefix search and trigram substring indexing. `unicode61 remove_diacritics 2` handles multiply accented Latin characters correctly; trigram queries shorter than three characters have limitations. [Official reference](https://www.sqlite.org/fts5.html) | Keep as a future candidate-retrieval option. Token filtering alone is not a replacement for fuzzy/joined-word matching, and must preserve recall before ranking. |
| Underthesea | Provides Vietnamese normalization, word segmentation and other NLP pipelines. [Project documentation](https://github.com/undertheseanlp/underthesea#vietnamese-nlp), [Apache-2.0 license](https://github.com/undertheseanlp/underthesea/blob/main/LICENSE) | Not installed. Our short filename queries need tolerance for missing spaces/typos rather than a general NLP pipeline. This is a scope decision, not a comparative speed claim. |
| ftfy | Repairs malformed Unicode and mojibake. [Official documentation](https://ftfy.readthedocs.io/en/latest/) | Not installed. Valid Vietnamese Unicode normalization is the current problem; automatic encoding repair is a separate requirement if corrupted text is observed. |

No additional runtime dependency is needed. No external service, model download or copied
third-party source is introduced. Existing MIT-licensed RapidFuzz supplies native matching.

## Problems reproduced in the previous implementation

- Dropping accents before ranking made `má`, `ma`, and `mà` indistinguishable; newer records
  could outrank the exact spelling requested by the user.
- `votay` worked, but `votya` and `catvotya` could miss `Cat vỗ tay` because the typo gate only
  compared a query word to separate stored syllables.
- Underscores were retained as word characters, so a pasted filename could miss its spaced title.

## Implemented search behavior

`domain/text.py` produces two immutable keys per text: an accented NFKC/casefolded form and an
accent-folded form using the existing `đ` → `d` mapping. Punctuation, underscores and whitespace
separate words; invisible format characters are removed for search. NFC/NFD-equivalent spellings
become comparable. Neither the display title nor persisted legacy keys are rewritten.

Ranking order is:

1. Exact accented spelling.
2. Exact accent-folded name.
3. Name keyword/joined-word matches.
4. Metadata keyword/joined-word matches.
5. Fuzzy matches supported by every query word.

Within a tier, relevance precedes accent similarity, then recency. Missing accents remain a
valid fallback. Ambiguous accentless queries can legitimately return several tone variants.

Fuzzy matching considers each word and up to three adjacent stored syllables joined together,
within a single field. Words of 3–6 characters allow at most one edit; longer words allow at
most two. Damerau–Levenshtein treats an adjacent character swap as one edit. Accepted matches
must have mean similarity at least 75/100. Queries shorter than four non-space characters use
literal matches only; fuzzy corrections of long joined phrases beyond three syllables remain
limited. There is no synonym inference, semantic search, OCR or automatic mojibake repair.

Only normalization is cached, through a bounded 16,384-entry `lru_cache`; each raw text stores
both keys together. [Python's cache reference](https://docs.python.org/3.14/library/functools.html#functools.lru_cache)
describes the thread-safe cache mechanism. Search results/record IDs are not cached, so edits
and removals are visible on the next query. SQL still applies guild/category filters first,
streams all candidates and limits results only after ranking. No database migration is required.

## Quality evaluation

The committed `VIETNAMESE_SEARCH_CASES` regression corpus contains 24 queries against 12 titles,
including deliberately confusing tone variants. Expected sets allow ambiguity for accentless
queries. This is a small requirements-driven corpus, not an independent estimate of accuracy
on all Vietnamese queries. Baseline: commit `76ec7a0`.

| Metric on these 24 queries | Before | After |
| --- | ---: | ---: |
| Expected result ranked first | 14/24 | 24/24 |
| Expected result in first five | 20/24 | 24/24 |

Additional tests cover query punctuation, Unicode composition, invisible characters, joined
word typos, metadata boundaries, short-query noise, old records, cross-guild/category isolation
and edit/delete freshness. The existing `votay` behavior is retained.

## Performance measurement

Environment: Python 3.14.4, RapidFuzz 3.14.6, SQLite 3.46.1 on the development machine. Synthetic
catalogs contain one early `Cat vỗ tay` record and numbered distractor titles, a shared caption
and a `reaction` category. Timing includes SQLite retrieval and ranking, `limit=5`. The following
comparison interleaved the baseline and new implementation, warmed each query once and used
seven measured samples per version. Values are medians in milliseconds.

| Rows | Query | Before | After |
| ---: | --- | ---: | ---: |
| 1,000 | `cat vo tay` | 21.88 | 21.55 |
| 1,000 | `votay` | 25.09 | 20.90 |
| 1,000 | `votya` | 28.68 | 23.56 |
| 1,000 | `zxqv blrp` | 25.87 | 19.96 |
| 1,000 | `reactoin` | 31.34 | 32.46 |
| 5,000 | `cat vo tay` | 112.24 | 85.72 |
| 5,000 | `votay` | 116.88 | 102.02 |
| 5,000 | `votya` | 115.06 | 99.91 |
| 5,000 | `zxqv blrp` | 113.07 | 89.71 |
| 5,000 | `reactoin` | 198.47 | 182.45 |

The old implementation returns no match for `votya`; its timing is not evidence of equivalent
search quality. Results vary with host load, cold/warm cache and data distribution. In a
separate current-only run, some 5,000-row queries took 125–241 ms. Not every query is faster,
and the scan remains linear; these are observations, not latency guarantees.

Run a current-version, synthetic-only benchmark without credentials or Discord requests:

```bash
source .venv/bin/activate
python scripts/benchmark_search.py --sizes 1000 5000 --repeats 7
```

The script uses disposable databases and never reads the real meme database. For larger
collections, measure p95 latency with representative captions and cache misses before adding
FTS5. Any future index must union candidate paths for exact, joined and typo queries; an exact
FTS-only prefilter would discard useful corrections before RapidFuzz can rank them.
