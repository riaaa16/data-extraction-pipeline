from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .errors import StructuredExtractionError
from .ollama_client import OllamaClient
from .schema import SchemaField


def extract_structured(
    entry: Mapping[str, object],
    schema_fields: List[SchemaField],
    client: OllamaClient,
    *,
    raw_response_dir: str | Path | None = None,
) -> Dict[str, object]:
    system_prompt, user_prompt = build_extraction_prompt(schema_fields, str(entry.get("raw_text", "")))
    result = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)

    try:
        parsed = _parse_model_object(result.content)
    except StructuredExtractionError as exc:
        output_path = _save_raw_response(result.content, entry.get("id"), raw_response_dir)
        raise StructuredExtractionError(
            f"{exc}. Raw response saved at: {output_path}"
        ) from exc

    if not isinstance(parsed, dict):
        output_path = _save_raw_response(result.content, entry.get("id"), raw_response_dir)
        raise StructuredExtractionError(
            "Model output was not a JSON object. "
            f"Raw response saved at: {output_path}"
        )

    row: Dict[str, object] = {
        "id": entry.get("id"),
        "raw_text": entry.get("raw_text"),
    }

    for field in schema_fields:
        raw_value = parsed.get(field.name)
        row[field.name] = _normalize_value(field, raw_value)

    row["_meta"] = {
        "model": result.model,
        "latency_ms": result.latency_ms,
        "prompt_eval_count": result.prompt_eval_count,
        "eval_count": result.eval_count,
    }

    return row


def extract_structured_batch(
    entries: List[Mapping[str, object]],
    schema_fields: List[SchemaField],
    client: OllamaClient,
    *,
    raw_response_dir: str | Path | None = None,
    show_progress: bool = True,
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    total = len(entries)
    for idx, entry in enumerate(entries, start=1):
        if show_progress:
            print(f"[llm] extracting {idx}/{total} (id={entry.get('id')})")

        row = extract_structured(
            entry,
            schema_fields,
            client,
            raw_response_dir=raw_response_dir,
        )
        rows.append(row)

    return rows


def build_extraction_prompt(schema_fields: List[SchemaField], raw_text: str) -> tuple[str, str]:
    field_instructions: List[str] = []
    for field in schema_fields:
        detail = f"- {field.name}: {field.type}"
        if field.type == "enum" and field.enum:
            detail += f" (one of: {', '.join(field.enum)})"
        if field.description:
            detail += f". {field.description}"
        field_instructions.append(detail)

    system_prompt = (
        "You extract structured fields from UX research text. "
        "Return a single JSON object and nothing else. "
        "Only use information explicitly present in the source text. "
        "If unknown, use null. Do not invent values."
    )

    user_prompt = (
        "Extract fields for this schema:\n"
        + "\n".join(field_instructions)
        + "\n\nRules:\n"
        + "- Output must be valid JSON object.\n"
        + "- Include exactly the schema field keys (no extra keys).\n"
        + "- Use null for missing values.\n"
        + "\nSource text:\n"
        + raw_text
    )

    return system_prompt, user_prompt


def _parse_model_object(raw_response: str) -> Dict[str, Any] | object:
    candidate = raw_response.strip()

    try:
        return json.loads(candidate)
    except Exception:
        pass

    # Guard for wrapped responses: try first '{' to last '}'.
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        snippet = candidate[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            pass

    raise StructuredExtractionError("Model output is not valid JSON")


def _normalize_value(field: SchemaField, value: object) -> object:
    if value is None:
        return None

    if field.type == "string":
        text = str(value).strip()
        return text if text else None

    if field.type == "number":
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return None

    if field.type == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "yes", "y", "1"}:
            return True
        if text in {"false", "no", "n", "0"}:
            return False
        return None

    if field.type == "enum":
        if not field.enum:
            return None
        text = str(value).strip()
        if not text:
            return None

        by_lower = {option.lower(): option for option in field.enum}
        return by_lower.get(text.lower())

    return None


def _save_raw_response(raw_response: str, entry_id: object, raw_response_dir: str | Path | None) -> Path:
    output_dir = Path(raw_response_dir or ".depipeline_logs/raw_responses")
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(entry_id or "unknown"))
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    file_path = output_dir / f"{safe_id}_{ts}.txt"
    file_path.write_text(raw_response, encoding="utf-8")
    return file_path