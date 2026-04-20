"""Data extraction pipeline.

Provides:
- `extract_text(path) -> str`
- `segment_entries(text) -> list[dict]`
- `extract_structured(entry, schema_fields, client) -> dict`

Later sprints will layer LLM extraction, validation, UI, and insights on top.
"""

from .extraction import extract_text
from .ollama_client import OllamaClient, OllamaConfig
from .schema import SchemaField, load_schema_file
from .segmentation import segment_entries
from .structured_extraction import extract_structured

__all__ = [
	"extract_text",
	"segment_entries",
	"extract_structured",
	"SchemaField",
	"load_schema_file",
	"OllamaClient",
	"OllamaConfig",
]
