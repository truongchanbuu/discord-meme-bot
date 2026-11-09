"""Vietnamese-aware relevance with exact, folded, joined and bounded typo matching."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from heapq import nlargest

from rapidfuzz import fuzz, process
from rapidfuzz.distance import DamerauLevenshtein

from meme_manager.domain.models import Meme
from meme_manager.domain.options import SearchOptions
from meme_manager.domain.repositories import MemeRepository
from meme_manager.domain.text import search_keys

EXACT_ACCENTED_NAME = 5
EXACT_NAME = 4
NAME_WORDS = 3
METADATA_WORDS = 2
FUZZY_WORDS = 1

RankedMeme = tuple[int, float, float, int, Meme]


@dataclass(frozen=True, slots=True)
class SearchQuery:
    accented: str
    folded: str
    words: tuple[str, ...]
    compact: str


class MemeSearchService:
    def __init__(self, repository: MemeRepository, options: SearchOptions) -> None:
        self.repository = repository
        self.options = options
        self._search_keys = lru_cache(maxsize=options.normalization_cache_entries)(search_keys)

    def search(
        self,
        guild_id: int,
        query: str,
        limit: int | None = None,
        *,
        channel_id: int | None = None,
        extensions: tuple[str, ...] | None = None,
    ) -> list[Meme]:
        keys = self._search_keys(query)
        accented = " ".join(keys.accented.split()[: self.options.max_query_words])
        folded = " ".join(keys.folded.split()[: self.options.max_query_words])
        if not folded:
            return []
        prepared = SearchQuery(accented, folded, tuple(folded.split()), folded.replace(" ", ""))
        candidates = self.repository.iter_search_candidates(
            guild_id, channel_id=channel_id, extensions=extensions
        )
        ranked = self._ranked_matches(candidates, prepared)
        limit = min(
            max(self.options.max_results if limit is None else limit, 1), self.options.max_results
        )
        return [match[-1] for match in nlargest(limit, ranked, key=lambda match: match[:4])]

    def _ranked_matches(
        self, candidates: Iterator[Meme], query: SearchQuery
    ) -> Iterator[RankedMeme]:
        for meme in candidates:
            keys = [
                self._search_keys(value)
                for value in (meme.title, meme.tags, meme.message_text, meme.channel_name)
            ]
            accented = [key.accented for key in keys]
            fields = [key.folded for key in keys]
            score = self._score(query, fields, accented)
            if score is not None:
                tier, similarity, accent_similarity = score
                yield tier, similarity, accent_similarity, meme.id, meme

    def _score(
        self, query: SearchQuery, fields: list[str], accented: list[str]
    ) -> tuple[int, float, float] | None:
        title = fields[0]
        if query.accented == accented[0]:
            return EXACT_ACCENTED_NAME, 100.0, 100.0
        if query.folded == title:
            return EXACT_NAME, 100.0, fuzz.WRatio(query.accented, accented[0])
        compact = [field.replace(" ", "") for field in fields]
        if all(word in compact[0] for word in query.words):
            return (
                NAME_WORDS,
                max(fuzz.WRatio(query.folded, title), fuzz.WRatio(query.compact, compact[0])),
                fuzz.WRatio(query.accented, accented[0]),
            )
        if all(any(word in field for field in compact) for word in query.words):
            return (
                METADATA_WORDS,
                max(fuzz.WRatio(query.compact, field) for field in compact),
                max(fuzz.WRatio(query.accented, field) for field in accented),
            )
        similarity = self._fuzzy_score(query, fields, compact)
        if similarity is None:
            return None
        return (
            FUZZY_WORDS,
            similarity,
            max(fuzz.WRatio(query.accented, field) for field in accented),
        )

    def _fuzzy_score(
        self, query: SearchQuery, fields: list[str], compact: list[str]
    ) -> float | None:
        if len(query.compact) < self.options.min_fuzzy_query_length:
            return None
        scores: list[float] = []
        for word in query.words:
            if any(word in field for field in compact):
                scores.append(100.0)
                continue
            if len(word) < self.options.min_fuzzy_word_length:
                return None
            # Bound edits by word length, not by a permissive partial-match score.
            budget = (
                self.options.short_word_edits
                if len(word) < self.options.long_word_length
                else self.options.long_word_edits
            )
            match = process.extractOne(
                word,
                self._word_candidates(fields, len(word), budget),
                scorer=DamerauLevenshtein.distance,
                score_cutoff=budget,
            )
            if match is None:
                return None
            scores.append(100.0 * (1 - match[1] / max(len(word), len(match[0]))))
        similarity = sum(scores) / len(scores)
        return similarity if similarity >= self.options.min_fuzzy_score else None

    def _word_candidates(self, fields: Sequence[str], length: int, budget: int) -> Iterator[str]:
        # Join adjacent syllables within one field only; never invent words across metadata.
        for field in fields:
            words = field.split()
            for start in range(len(words)):
                joined = ""
                for stop in range(start, min(start + self.options.max_joined_words, len(words))):
                    joined += words[stop]
                    if len(joined) > length + budget:
                        break
                    if len(joined) >= length - budget:
                        yield joined
