from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from .errors import DepipelineError

from .normalize import normalize_text


_BLANKLINE_SPLIT = re.compile(r"\n\s*\n+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_BULLET_LINE = re.compile(r"^\s*(?:[-*•]|(?:\d+|[a-zA-Z])[.)])\s+")
_TABLE_GAP_SPLIT = re.compile(r"\s{2,}")
_ANCHOR_LINE = re.compile(
    r"^\s*(?:participant|respondent|interviewee|user|record|entry|case|ticket|id|date|time|session|source|platform|topic|title)\s*[:#-]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Block:
    kind: str
    text: str


def segment_entries(
    text: str,
    *,
    min_entry_chars: int = 20,
    merge_below_chars: int = 40,
    target_entry_chars: int = 650,
) -> List[Dict[str, object]]:
    """Segment extracted text into entry-like chunks.

    Strategy (deterministic):
    - Parse text into structure-aware blocks (anchors, bullets, tables, paragraphs)
    - Split on likely entry boundaries (anchor transitions and record-like blocks)
    - Expand bullet-only and table blocks into multiple entries when they look like records
    - Fall back to sentence-window splitting for dense text with weak/no delimiters
    - Merge very small chunks with neighbors to avoid fragments
    - Drop empty chunks

    Returns a list of dicts: {"id": int, "raw_text": str}
    """

    text = normalize_text(text)
    if not text:
        return []

    blocks = _build_blocks(text)
    chunks = _chunks_from_blocks(blocks, min_entry_chars=min_entry_chars)

    # Dense no-delimiter fallback: if we only found one giant chunk, split by sentences.
    if len(chunks) <= 1 and len(text) >= target_entry_chars * 2:
        chunks = _split_dense_text(text, target_entry_chars=target_entry_chars)

    merged = _merge_small_chunks(chunks, merge_below_chars=merge_below_chars)
    final_chunks = [c for c in merged if len(c) >= min_entry_chars]

    return [
        {
            "id": index,
            "raw_text": chunk,
        }
        for index, chunk in enumerate(final_chunks, start=1)
    ]


def segment_entries_llm(
    text: str,
    client: object,
    *,
    dataset_description: str | None = None,
    min_entry_chars: int = 20,
    max_entries: int = 200,
) -> List[Dict[str, object]]:
    """Use an LLM (via an Ollama-like client) to split text into entries.

    The client must provide: chat_json(system_prompt=..., user_prompt=...) -> result with .content.
    The returned .content must be valid JSON.

    Returns list of dicts: {"id": int, "raw_text": str}.
    """

    text = normalize_text(text)
    if not text:
        return []

    if len(text) > 120_000:
        raise DepipelineError(
            "Input text is too large for LLM entry separation; use deterministic segmentation"
        )

    # Prompt explicitly asks for a lossless split: preserve original text, no rewriting.
    dataset_hint = normalize_text(dataset_description or "").strip()
    dataset_clause = (
        f"\nDataset description (from user):\n{dataset_hint}\n" if dataset_hint else ""
    )

    system_prompt = (
        "You split a single document into discrete entries (records). "
        "Return ONLY valid JSON. Do not include markdown.\n\n"
        "Rules:\n"
        "- Output schema: {\"entries\": [{\"raw_text\": <string>}, ...]}\n"
        "- Preserve original text inside each raw_text exactly (no rewriting, no summarizing).\n"
        "- Keep entries in original order and cover the entire input (no omissions).\n"
        "- Split entries based on explicit boundaries in the text (headers, IDs, timestamps, separators, bullets).\n"
        "- Do NOT merge distinct records into one entry.\n"
        "- Each entry should be a coherent unit that can be extracted independently.\n"
        + dataset_clause
    )
    user_prompt = f"Split this text into entries:\n\n{text}"

    try:
        result = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        payload = _parse_llm_entries_payload(result.content)
    except DepipelineError:
        raise
    except Exception as exc:
        raise DepipelineError(f"LLM entry separation failed: {exc}") from exc

    entries = _coerce_entries_list(payload, min_entry_chars=min_entry_chars)
    if not entries:
        raise DepipelineError("LLM returned zero entries")

    if len(entries) > max_entries:
        raise DepipelineError(f"LLM returned too many entries ({len(entries)} > {max_entries})")

    return [
        {
            "id": index,
            "raw_text": entry,
        }
        for index, entry in enumerate(entries, start=1)
    ]


def segment_entries_regex(
    text: str,
    start_patterns: List[str],
    *,
    min_entry_chars: int = 20,
    merge_below_chars: int = 40,
) -> List[Dict[str, object]]:
    """Split entries using user-supplied regex start-of-entry patterns.

    Each regex is applied with re.MULTILINE; every match start is treated as a
    new entry boundary. Returns list of dicts: {"id": int, "raw_text": str}.
    """

    text = normalize_text(text)
    if not text:
        return []

    patterns = [p.strip() for p in start_patterns if p.strip()]
    if not patterns:
        raise DepipelineError("No regex patterns provided for entry separation")

    start_offsets: List[int] = []
    for pattern in patterns:
        try:
            regex = re.compile(pattern, re.MULTILINE)
        except re.error as exc:
            raise DepipelineError(f"Invalid regex pattern: {pattern} ({exc})") from exc

        for match in regex.finditer(text):
            start_offsets.append(match.start())

    if not start_offsets:
        raise DepipelineError("No entry boundaries matched the provided regex patterns")

    if 0 not in start_offsets:
        start_offsets.append(0)

    ordered = sorted(set(start_offsets))
    chunks: List[str] = []
    for idx, start in enumerate(ordered):
        end = ordered[idx + 1] if idx + 1 < len(ordered) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

    merged = _merge_small_chunks(chunks, merge_below_chars=merge_below_chars)
    final_chunks = [c for c in merged if len(c) >= min_entry_chars]

    return [
        {
            "id": index,
            "raw_text": chunk,
        }
        for index, chunk in enumerate(final_chunks, start=1)
    ]


def segment_entries_llm_boundaries(
    text: str,
    client: object,
    *,
    dataset_description: str | None = None,
    min_entry_chars: int = 20,
    max_entries: int = 200,
) -> List[Dict[str, object]]:
    """Use an LLM to return entry boundaries only (line ranges).

    The LLM must return JSON: {"entries": [{"start_line": <int>, "end_line": <int>}, ...]}.
    Line numbers are 1-based and inclusive, based on the normalized input text.
    """

    text = normalize_text(text)
    if not text:
        return []

    if len(text) > 120_000:
        raise DepipelineError(
            "Input text is too large for LLM entry separation; use deterministic or regex segmentation"
        )

    lines = text.split("\n")
    numbered_lines = "\n".join(f"{idx + 1}| {line}" for idx, line in enumerate(lines))

    dataset_hint = normalize_text(dataset_description or "").strip()
    dataset_clause = (
        f"\nDataset description (from user):\n{dataset_hint}\n" if dataset_hint else ""
    )

    system_prompt = (
        "You split a single document into discrete entries and return ONLY boundaries. "
        "Return ONLY valid JSON. Do not include markdown.\n\n"
        "Rules:\n"
        "- Output schema: {\"entries\": [{\"start_line\": <int>, \"end_line\": <int>}, ...]}\n"
        "- Line numbers are 1-based and refer to the numbered input lines.\n"
        "- Keep entries in original order and cover the entire input (no omissions).\n"
        "- Do NOT merge distinct records into one entry.\n"
        "- Each entry should be a coherent unit that can be extracted independently.\n"
        + dataset_clause
    )

    user_prompt = (
        "Split the following numbered lines into entry boundaries. "
        "Return ONLY JSON with start_line/end_line.\n\n"
        f"{numbered_lines}"
    )

    try:
        result = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        payload = _parse_llm_entries_payload(result.content)
    except DepipelineError:
        raise
    except Exception as exc:
        raise DepipelineError(f"LLM entry separation failed: {exc}") from exc

    ranges = _coerce_llm_line_ranges(payload, max_lines=len(lines))
    if not ranges:
        raise DepipelineError("LLM returned zero entry boundaries")
    if len(ranges) > max_entries:
        raise DepipelineError(f"LLM returned too many entries ({len(ranges)} > {max_entries})")

    entries: List[str] = []
    for start, end in ranges:
        chunk = "\n".join(lines[start - 1:end]).strip()
        if len(chunk) >= min_entry_chars:
            entries.append(chunk)

    if not entries:
        raise DepipelineError("LLM entry boundaries produced no usable entries")

    return [
        {
            "id": index,
            "raw_text": entry,
        }
        for index, entry in enumerate(entries, start=1)
    ]


def _parse_llm_entries_payload(content: str) -> Any:
    try:
        import json

        return json.loads(content)
    except Exception as exc:
        raise DepipelineError("LLM did not return valid JSON") from exc


def _coerce_entries_list(payload: Any, *, min_entry_chars: int) -> List[str]:
    """Accept a few JSON shapes and return a list of entry raw_text strings."""

    raw_items: Any
    if isinstance(payload, dict) and "entries" in payload:
        raw_items = payload["entries"]
    else:
        raw_items = payload

    if not isinstance(raw_items, list):
        raise DepipelineError("LLM JSON must be a list or an object with an 'entries' list")

    entries: List[str] = []
    for item in raw_items:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("raw_text")
        else:
            text = None

        if not isinstance(text, str):
            continue

        normalized = normalize_text(text)
        if len(normalized) >= min_entry_chars:
            entries.append(normalized)

    return entries


def _coerce_llm_line_ranges(payload: Any, *, max_lines: int) -> List[tuple[int, int]]:
    raw_items: Any
    if isinstance(payload, dict) and "entries" in payload:
        raw_items = payload["entries"]
    else:
        raw_items = payload

    if not isinstance(raw_items, list):
        raise DepipelineError("LLM JSON must be a list or an object with an 'entries' list")

    ranges: List[tuple[int, int]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        start = item.get("start_line")
        end = item.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start < 1 or end < start or end > max_lines:
            continue
        ranges.append((start, end))

    return ranges


def _build_blocks(text: str) -> List[_Block]:
    blocks: List[_Block] = []

    for part in [p.strip() for p in _BLANKLINE_SPLIT.split(text) if p.strip()]:
        lines = [line.rstrip() for line in part.split("\n") if line.strip()]
        if not lines:
            continue

        if all(_is_bullet_line(line) for line in lines):
            blocks.append(_Block(kind="bullet", text="\n".join(lines).strip()))
            continue

        if _looks_like_table(lines):
            blocks.append(_Block(kind="table", text="\n".join(lines).strip()))
            continue

        if _looks_like_anchor_part(lines):
            blocks.append(_Block(kind="anchor", text="\n".join(lines).strip()))
            continue

        blocks.append(_Block(kind="paragraph", text="\n".join(lines).strip()))

    return blocks


def _chunks_from_blocks(blocks: List[_Block], *, min_entry_chars: int) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []

    for block in blocks:
        if block.kind == "table":
            table_rows = _expand_table_rows(block.text)
            if len(table_rows) > 1:
                if current:
                    chunks.append("\n\n".join(current).strip())
                    current = []
                chunks.extend(table_rows)
                continue

        if block.kind == "bullet":
            bullet_entries = _expand_bullet_entries(block.text, min_entry_chars=min_entry_chars)
            if len(bullet_entries) > 1:
                if current:
                    chunks.append("\n\n".join(current).strip())
                    current = []
                chunks.extend(bullet_entries)
                continue

        if block.kind == "anchor" and current and len("\n\n".join(current)) >= min_entry_chars:
            chunks.append("\n\n".join(current).strip())
            current = [block.text]
            continue

        current.append(block.text)

    if current:
        chunks.append("\n\n".join(current).strip())

    return [c for c in chunks if c.strip()]


def _merge_small_chunks(chunks: List[str], *, merge_below_chars: int) -> List[str]:
    if not chunks:
        return []

    merged: List[str] = []
    i = 0
    while i < len(chunks):
        current = chunks[i]

        if len(current) < merge_below_chars and i + 1 < len(chunks):
            current = f"{current}\n\n{chunks[i + 1]}".strip()
            i += 2
        else:
            i += 1

        if merged and len(current) < merge_below_chars:
            merged[-1] = f"{merged[-1]}\n\n{current}".strip()
        else:
            merged.append(current)

    return merged


def _split_dense_text(text: str, *, target_entry_chars: int) -> List[str]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if len(sentences) <= 1:
        return [text]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence)
        if current and current_len + sentence_len > target_entry_chars:
            chunks.append(" ".join(current).strip())
            current = [sentence]
            current_len = sentence_len
        else:
            current.append(sentence)
            current_len += sentence_len

    if current:
        chunks.append(" ".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def _is_bullet_line(line: str) -> bool:
    return bool(_BULLET_LINE.match(line))


def _looks_like_anchor_part(lines: List[str]) -> bool:
    anchor_count = sum(1 for line in lines if _ANCHOR_LINE.match(line))
    return anchor_count >= 2 or (anchor_count == 1 and len(lines) <= 2)


def _looks_like_table(lines: List[str]) -> bool:
    row_like = 0
    for line in lines:
        if len(_split_columns(line)) >= 2:
            row_like += 1
    return row_like >= 2


def _split_columns(line: str) -> List[str]:
    stripped = line.strip()
    if not stripped:
        return []

    if "|" in stripped:
        return [col.strip() for col in stripped.split("|") if col.strip()]
    if "\t" in stripped:
        return [col.strip() for col in stripped.split("\t") if col.strip()]

    return [col.strip() for col in _TABLE_GAP_SPLIT.split(stripped) if col.strip()]


def _expand_table_rows(table_text: str) -> List[str]:
    lines = [line.strip() for line in table_text.split("\n") if line.strip()]
    if len(lines) < 2:
        return [table_text.strip()]

    header = lines[0]
    header_cols = _split_columns(header)
    if len(header_cols) < 2:
        return [table_text.strip()]

    rows = lines[1:]
    normalized_rows: List[str] = []
    for row in rows:
        row_cols = _split_columns(row)
        if len(row_cols) < 2:
            continue
        normalized_rows.append(f"{header}\n{row}".strip())

    if len(normalized_rows) >= 2:
        return normalized_rows
    return [table_text.strip()]


def _expand_bullet_entries(bullet_text: str, *, min_entry_chars: int) -> List[str]:
    bullets = [line.strip() for line in bullet_text.split("\n") if line.strip()]
    cleaned = [_BULLET_LINE.sub("", line).strip() for line in bullets]
    candidates = [line for line in cleaned if len(line) >= max(10, min_entry_chars // 2)]

    # Split only if this clearly looks like multiple records.
    if len(candidates) >= 3:
        return candidates
    return [bullet_text.strip()]
