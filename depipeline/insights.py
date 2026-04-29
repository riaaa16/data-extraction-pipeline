from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
import re
from typing import Any, Dict, Iterable, List, Tuple

from .schema import SchemaField


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "he",
    "her",
    "his",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "me",
    "my",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "she",
    "so",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "to",
    "too",
    "up",
    "us",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "who",
    "why",
    "will",
    "with",
    "you",
    "your",
}


@dataclass(frozen=True)
class KeywordCount:
    keyword: str
    count: int


@dataclass(frozen=True)
class ThemeCount:
    theme: str
    count: int


@dataclass(frozen=True)
class Insights:
    keywords: List[KeywordCount]
    themes: List[ThemeCount]
    field_breakdowns: Dict[str, List[Tuple[str, int]]]


def compute_insights(
    rows: List[Dict[str, Any]],
    schema_fields: List[SchemaField],
    *,
    max_keywords: int = 25,
    max_themes: int = 12,
    max_breakdown_values: int = 12,
    max_field_distinct: int = 25,
) -> Insights:
    """Compute lightweight, deterministic insights over extracted rows.

    - Keywords: simple token frequency over `raw_text`.
    - Themes: deterministic bucketing by simple stems over top keywords.
    - Field breakdowns: counts by low-cardinality fields present in schema.

    This is intentionally explainable and fast; no heavy modeling or LLM calls.
    """

    keyword_counts = _keyword_frequency(_iter_raw_text(rows))
    keywords = [
        KeywordCount(keyword=word, count=count)
        for word, count in keyword_counts.most_common(max_keywords)
    ]

    themes = _themes_from_keywords(keyword_counts, max_themes=max_themes)

    field_breakdowns: Dict[str, List[Tuple[str, int]]] = {}
    for field in schema_fields:
        breakdown = _field_breakdown(
            rows,
            field,
            max_values=max_breakdown_values,
            max_distinct=max_field_distinct,
        )
        if breakdown:
            field_breakdowns[field.name] = breakdown

    return Insights(keywords=keywords, themes=themes, field_breakdowns=field_breakdowns)


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{1,}")


def _iter_raw_text(rows: Iterable[Dict[str, Any]]) -> Iterable[str]:
    for row in rows:
        raw = row.get("raw_text")
        if isinstance(raw, str) and raw.strip():
            yield raw


def _keyword_frequency(texts: Iterable[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        for token in _WORD_RE.findall(text.lower()):
            token = token.strip("-'\"")
            if len(token) < 3:
                continue
            if token in _STOPWORDS:
                continue
            # Avoid counting pure punctuation-like artifacts.
            if not re.search(r"[a-z]", token):
                continue
            counter[token] += 1
    return counter


def _simple_stem(token: str) -> str:
    word = token.lower().strip("-'\"")
    if word.endswith("'s") and len(word) > 4:
        word = word[:-2]

    # A tiny, deterministic stemmer: enough to group plurals/verb forms.
    for suffix in ("ing", "ed", "ies", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            if suffix == "ies":
                return word[:-3] + "y"
            return word[: -len(suffix)]

    return word


def _themes_from_keywords(
    keyword_counts: Counter[str],
    *,
    max_themes: int,
    top_k_source: int = 50,
) -> List[ThemeCount]:
    if not keyword_counts:
        return []

    top_keywords = [w for w, _ in keyword_counts.most_common(top_k_source)]

    buckets: Dict[str, List[str]] = {}
    for keyword in top_keywords:
        stem = _simple_stem(keyword)
        buckets.setdefault(stem, []).append(keyword)

    themes: List[ThemeCount] = []
    for stem, words in buckets.items():
        # Theme label is the most common surface form in this bucket.
        label = max(words, key=lambda w: (keyword_counts[w], -len(w), w))
        total = sum(keyword_counts[w] for w in set(words))
        themes.append(ThemeCount(theme=label, count=int(total)))

    themes.sort(key=lambda t: (-t.count, t.theme))
    return themes[:max_themes]


def _field_breakdown(
    rows: List[Dict[str, Any]],
    field: SchemaField,
    *,
    max_values: int,
    max_distinct: int,
) -> List[Tuple[str, int]]:
    counts: Counter[str] = Counter()

    for row in rows:
        value = row.get(field.name)
        if value is None:
            continue

        if isinstance(value, bool):
            counts[str(value).lower()] += 1
            continue

        if isinstance(value, (int, float)):
            # Numeric fields are usually high-cardinality; only include if low distinct.
            counts[str(value)] += 1
            continue

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                continue
            counts[cleaned] += 1
            continue

        # Any other value type (lists, dicts, etc.) is ignored for breakdowns.

    if not counts:
        return []

    if len(counts) > max_distinct:
        return []

    return counts.most_common(max_values)
