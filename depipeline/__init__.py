"""Data extraction pipeline (Sprint 01 foundation).

Provides:
- `extract_text(path) -> str`
- `segment_entries(text) -> list[dict]`

Later sprints will layer LLM extraction, validation, UI, and insights on top.
"""

from .extraction import extract_text
from .segmentation import segment_entries

__all__ = ["extract_text", "segment_entries"]
