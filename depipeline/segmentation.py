from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

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
