from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .errors import StructuredExtractionError
from .ollama_client import OllamaClient
from .schema import SchemaField
from .validation import ValidationIssue, validate_model_object


@dataclass(frozen=True)
class ExtractionRunReport:
    total_entries: int
    valid_first_pass: int
    retried: int
    failed: int

    def as_dict(self) -> Dict[str, int]:
        return {
            "total_entries": self.total_entries,
            "valid_first_pass": self.valid_first_pass,
            "retried": self.retried,
            "failed": self.failed,
        }


def extract_structured(
    entry: Mapping[str, object],
    schema_fields: List[SchemaField],
    client: OllamaClient,
    *,
    raw_response_dir: str | Path | None = None,
    repair_instructions: List[str] | None = None,
) -> Dict[str, object]:
    parsed, result = _extract_model_object(
        entry,
        schema_fields,
        client,
        raw_response_dir=raw_response_dir,
        repair_instructions=repair_instructions,
    )

    return _row_from_model_object(entry, schema_fields, parsed, result)


def extract_structured_batch(
    entries: List[Mapping[str, object]],
    schema_fields: List[SchemaField],
    client: OllamaClient,
    *,
    raw_response_dir: str | Path | None = None,
    show_progress: bool = True,
) -> tuple[List[Dict[str, object]], Dict[str, int]]:
    return extract_structured_batch_with_validation(
        entries,
        schema_fields,
        client,
        raw_response_dir=raw_response_dir,
        show_progress=show_progress,
        max_retries=0,
    )


def extract_structured_batch_with_validation(
    entries: List[Mapping[str, object]],
    schema_fields: List[SchemaField],
    client: OllamaClient,
    *,
    raw_response_dir: str | Path | None = None,
    show_progress: bool = True,
    max_retries: int = 2,
) -> tuple[List[Dict[str, object]], Dict[str, int]]:
    rows: List[Dict[str, object]] = []
    report = ExtractionRunReport(
        total_entries=len(entries),
        valid_first_pass=0,
        retried=0,
        failed=0,
    )

    valid_first_pass = 0
    retried = 0
    failed = 0

    total = len(entries)
    for idx, entry in enumerate(entries, start=1):
        row, was_first_pass, used_retry, did_fail = _extract_entry_with_validation(
            entry,
            schema_fields,
            client,
            raw_response_dir=raw_response_dir,
            show_progress=show_progress,
            progress_index=idx,
            progress_total=total,
            max_retries=max_retries,
        )
        rows.append(row)

        if was_first_pass:
            valid_first_pass += 1
        if used_retry:
            retried += 1
        if did_fail:
            failed += 1

    report = ExtractionRunReport(
        total_entries=len(entries),
        valid_first_pass=valid_first_pass,
        retried=retried,
        failed=failed,
    )
    return rows, report.as_dict()


def _extract_entry_with_validation(
    entry: Mapping[str, object],
    schema_fields: List[SchemaField],
    client: OllamaClient,
    *,
    raw_response_dir: str | Path | None,
    show_progress: bool,
    progress_index: int,
    progress_total: int,
    max_retries: int,
) -> tuple[Dict[str, object], bool, bool, bool]:
    prior_signatures: set[str] = set()
    validation_issues: List[ValidationIssue] = []
    last_error = ""

    for attempt in range(max_retries + 1):
        if show_progress:
            print(
                f"[llm] extracting {progress_index}/{progress_total} "
                f"(id={entry.get('id')}, attempt={attempt + 1}/{max_retries + 1})"
            )

        repair_instructions = _build_repair_instructions(validation_issues, last_error)

        try:
            model_obj, result = _extract_model_object(
                entry,
                schema_fields,
                client,
                raw_response_dir=raw_response_dir,
                repair_instructions=repair_instructions,
            )
        except StructuredExtractionError as exc:
            last_error = str(exc)
            signature = f"parse:{_signature_text(last_error)}"
            if signature in prior_signatures or attempt >= max_retries:
                return _failed_row(
                    entry,
                    schema_fields,
                    retries_used=attempt,
                    error_message=last_error,
                    validation_issues=[],
                ), False, attempt > 0, True
            prior_signatures.add(signature)
            continue

        validation = validate_model_object(model_obj, schema_fields)
        if validation.valid:
            row = _row_from_model_object(entry, schema_fields, model_obj, result)
            confidence, reason_codes = _compute_confidence(
                retries_used=attempt,
                missing_fields=validation.missing_fields,
                type_coercions=validation.type_coercions,
            )
            row["confidence"] = confidence
            row.setdefault("_meta", {})
            row["_meta"]["status"] = "ok"
            row["_meta"]["retries"] = attempt
            row["_meta"]["validation"] = {
                "missing_fields": validation.missing_fields,
                "type_coercions": validation.type_coercions,
                "issues": [],
            }
            row["_meta"]["confidence_reason_codes"] = reason_codes
            return row, attempt == 0, attempt > 0, False

        validation_issues = validation.issues
        last_error = "; ".join(issue.message for issue in validation_issues)
        signature = "validation:" + "|".join(
            sorted(f"{issue.field}:{issue.code}" for issue in validation_issues)
        )

        if signature in prior_signatures or attempt >= max_retries:
            return _failed_row(
                entry,
                schema_fields,
                retries_used=attempt,
                error_message=last_error,
                validation_issues=validation_issues,
            ), False, attempt > 0, True

        prior_signatures.add(signature)

    return _failed_row(
        entry,
        schema_fields,
        retries_used=max_retries,
        error_message="Validation failed after retries",
        validation_issues=validation_issues,
    ), False, max_retries > 0, True


def build_extraction_prompt(
    schema_fields: List[SchemaField],
    raw_text: str,
    *,
    repair_instructions: List[str] | None = None,
) -> tuple[str, str]:
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
        + ("\n" + "\n".join(repair_instructions) + "\n" if repair_instructions else "")
        + "\nSource text:\n"
        + raw_text
    )

    return system_prompt, user_prompt


def _extract_model_object(
    entry: Mapping[str, object],
    schema_fields: List[SchemaField],
    client: OllamaClient,
    *,
    raw_response_dir: str | Path | None,
    repair_instructions: List[str] | None,
) -> tuple[Dict[str, Any], Any]:
    system_prompt, user_prompt = build_extraction_prompt(
        schema_fields,
        str(entry.get("raw_text", "")),
        repair_instructions=repair_instructions,
    )
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

    return parsed, result


def _row_from_model_object(
    entry: Mapping[str, object],
    schema_fields: List[SchemaField],
    model_obj: Dict[str, Any],
    result: Any,
) -> Dict[str, object]:
    row: Dict[str, object] = {
        "id": entry.get("id"),
        "raw_text": entry.get("raw_text"),
    }

    for field in schema_fields:
        raw_value = model_obj.get(field.name)
        row[field.name] = _normalize_value(field, raw_value)

    row["_meta"] = {
        "model": result.model,
        "latency_ms": result.latency_ms,
        "prompt_eval_count": result.prompt_eval_count,
        "eval_count": result.eval_count,
    }
    return row


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


def _build_repair_instructions(
    validation_issues: List[ValidationIssue],
    last_error: str,
) -> List[str] | None:
    if not validation_issues and not last_error:
        return None

    if validation_issues:
        lines = [
            "Previous attempt failed validation. Correct these issues and return JSON only:",
        ]
        lines.extend(
            [f"- {issue.field}: {issue.message}" for issue in validation_issues]
        )
        return lines

    return [
        "Previous attempt failed parsing.",
        f"Parse error: {last_error}",
        "Return only a valid JSON object with exactly the schema keys.",
    ]


def _compute_confidence(
    *,
    retries_used: int,
    missing_fields: int,
    type_coercions: int,
) -> tuple[float, List[str]]:
    score = 1.0
    score -= 0.18 * retries_used
    score -= 0.07 * missing_fields
    score -= 0.05 * type_coercions

    score = max(0.0, min(1.0, score))
    reason_codes: List[str] = []

    if retries_used:
        reason_codes.append(f"retries:{retries_used}")
    if missing_fields:
        reason_codes.append(f"missing_fields:{missing_fields}")
    if type_coercions:
        reason_codes.append(f"type_coercions:{type_coercions}")

    if not reason_codes:
        reason_codes.append("clean_first_pass")

    return round(score, 4), reason_codes


def _failed_row(
    entry: Mapping[str, object],
    schema_fields: List[SchemaField],
    *,
    retries_used: int,
    error_message: str,
    validation_issues: List[ValidationIssue],
) -> Dict[str, object]:
    row: Dict[str, object] = {
        "id": entry.get("id"),
        "raw_text": entry.get("raw_text"),
        "confidence": 0.0,
        "_meta": {
            "status": "failed",
            "retries": retries_used,
            "error": error_message,
            "validation": {
                "missing_fields": 0,
                "type_coercions": 0,
                "issues": [
                    {"field": issue.field, "code": issue.code, "message": issue.message}
                    for issue in validation_issues
                ],
            },
            "confidence_reason_codes": ["failed_validation_or_parse"],
        },
    }

    for field in schema_fields:
        row[field.name] = None

    return row


def _signature_text(message: str) -> str:
    return message[:160].strip().lower()