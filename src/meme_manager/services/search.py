"""Rank exact, keyword and typo-tolerant meme matches within a repository scope."""

from collections.abc import Iterator
from heapq import nlargest

from rapidfuzz import fuzz, process

from meme_manager.domain.models import Meme
from meme_manager.domain.repositories import MemeRepository
from meme_manager.domain.text import normalize

MAX_SEARCH_RESULTS = 100
MAX_QUERY_WORDS = 12
MIN_FUZZY_QUERY_LENGTH = 4
MIN_FUZZY_SCORE = 75.0
MIN_WORD_SCORE = 60.0

EXACT_NAME = 4
NAME_WORDS = 3
METADATA_WORDS = 2
FUZZY_WORDS = 1

RankedMeme = tuple[int, float, int, Meme]


class MemeSearchService:
    def __init__(self, repository: MemeRepository) -> None:
        self.repository = repository

    def search(
        self,
        guild_id: int,
        query: str,
        limit: int = MAX_SEARCH_RESULTS,
        *,
        channel_id: int | None = None,
    ) -> list[Meme]:
        words = normalize(query).split()[:MAX_QUERY_WORDS]
        if not words or not any(character.isalnum() for character in query):
            return []
        query = " ".join(words)
        limit = min(max(limit, 1), MAX_SEARCH_RESULTS)
        candidates = self.repository.iter_search_candidates(guild_id, channel_id=channel_id)
        ranked = self._ranked_matches(candidates, query, words)
        best = nlargest(limit, ranked, key=lambda match: match[:3])
        return [match[3] for match in best]

    def _ranked_matches(
        self, candidates: Iterator[Meme], query: str, words: list[str]
    ) -> Iterator[RankedMeme]:
        for meme in candidates:
            score = self._score(meme, query, words)
            if score is not None:
                tier, similarity = score
                yield tier, similarity, meme.id, meme

    def _score(self, meme: Meme, query: str, words: list[str]) -> tuple[int, float] | None:
        title = meme.name_index or normalize(meme.title)
        fields = [
            title,
            normalize(meme.tags),
            normalize(meme.message_text),
            normalize(meme.channel_name),
        ]
        combined = " ".join(fields)
        compact_fields = [field.replace(" ", "") for field in fields]
        compact_query = query.replace(" ", "")
        if query == title:
            return EXACT_NAME, 100.0
        if all(word in compact_fields[0] for word in words):
            return NAME_WORDS, max(
                fuzz.WRatio(query, title), fuzz.WRatio(compact_query, compact_fields[0])
            )
        if all(any(word in field for field in compact_fields) for word in words):
            return METADATA_WORDS, max(
                fuzz.WRatio(compact_query, field) for field in compact_fields
            )
        if len(query.replace(" ", "")) < MIN_FUZZY_QUERY_LENGTH:
            return None

        # Require support for every word; one common word must not admit unrelated queries.
        terms = combined.split()
        for word in words:
            if any(word in term for term in terms):
                continue
            if len(word) < 3:
                return None
            match = process.extractOne(word, terms, scorer=fuzz.ratio, score_cutoff=MIN_WORD_SCORE)
            if match is None:
                return None
        match = process.extractOne(
            query, [*fields, combined], scorer=fuzz.WRatio, score_cutoff=MIN_FUZZY_SCORE
        )
        if match is None:
            return None
        return FUZZY_WORDS, float(match[1])
