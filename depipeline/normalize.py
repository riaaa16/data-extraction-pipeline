from __future__ import annotations

import re


_BLANKLINES_3PLUS = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Normalize text for downstream segmentation.

    - Normalize newlines (CRLF/CR -> LF)
    - Strip trailing whitespace per line
    - Collapse 3+ consecutive newlines to 2 (preserves paragraph breaks)
    """

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")

    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines).strip()

    text = _BLANKLINES_3PLUS.sub("\n\n", text)
    return text
