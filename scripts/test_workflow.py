from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from depipeline.extraction import extract_text_with_diagnostics
from depipeline.ollama_client import OllamaResult
from depipeline.schema import SchemaField, load_schema_file
from depipeline.segmentation import segment_entries
from depipeline.structured_extraction import extract_structured_batch_with_validation


class _FakeWorkflowClient:
    """Deterministic fake client to validate the workflow without Ollama."""

    _DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
    _STEP_RE = re.compile(r"step\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)
    _PARTICIPANT_RE = re.compile(r"participant\s*:\s*([A-Za-z][A-Za-z\- ]+)", re.IGNORECASE)

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> OllamaResult:
        source_text = user_prompt.split("\nSource text:\n", 1)[-1]
        text_lower = source_text.lower()

        participant_match = self._PARTICIPANT_RE.search(source_text)
        participant_name = participant_match.group(1).strip() if participant_match else "Unknown"

        date_match = self._DATE_RE.search(source_text)
        entry_date = date_match.group(0) if date_match else None

        step_match = self._STEP_RE.search(source_text)
        if step_match:
            step_current = int(step_match.group(1))
            step_total = int(step_match.group(2))
        else:
            step_current = None
            step_total = None

        mentions_confusion = "confus" in text_lower or "friction" in text_lower

        if "onboarding" in text_lower:
            primary_issue = "onboarding"
        elif "filter" in text_lower:
            primary_issue = "filters"
        elif "search" in text_lower:
            primary_issue = "search"
        else:
            primary_issue = "other"

        sentiment = "negative" if mentions_confusion else "neutral"

        payload = {
            "participant_name": participant_name,
            "entry_date": entry_date,
            "flow_step_current": step_current,
            "flow_step_total": step_total,
            "sentiment": sentiment,
            "primary_issue": primary_issue,
            "mentions_confusion": mentions_confusion,
        }

        content = json.dumps(payload)
        return OllamaResult(
            content=content,
            model="workflow-fake-model",
            latency_ms=1,
            prompt_eval_count=1,
            eval_count=1,
            raw={"message": {"content": content}},
        )


def _rows_to_csv_bytes(rows: List[Dict[str, object]], schema_fields: List[SchemaField]) -> bytes:
    columns = ["id", "raw_text"] + [field.name for field in schema_fields] + ["confidence"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col) for col in columns})
    return buffer.getvalue().encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    root = ROOT
    core = root / "fixtures" / "core"
    schema_path = root / "fixtures" / "schemas" / "schema.typed.sample.json"

    file_paths = [
        core / "sample.txt",
        core / "sample.docx",
        core / "sample.pdf",
    ]

    for path in file_paths:
        _require(path.exists(), f"Required fixture missing: {path}")

    schema_fields = load_schema_file(schema_path)
    all_entries: List[Dict[str, object]] = []
    warnings: List[str] = []

    for path in file_paths:
        diagnostics = extract_text_with_diagnostics(path)
        warnings.extend([f"{path.name}: {w}" for w in diagnostics.warnings])
        entries = segment_entries(diagnostics.text)
        _require(len(entries) > 0, f"No entries produced for {path.name}")

        for entry in entries:
            entry["id"] = f"{path.stem}-{path.suffix.lstrip('.')}-{entry['id']}"
        all_entries.extend(entries)

    _require(len(all_entries) > 0, "No entries extracted from workflow inputs")

    rows, report = extract_structured_batch_with_validation(
        all_entries,
        schema_fields,
        _FakeWorkflowClient(),
        show_progress=False,
        max_retries=1,
    )

    _require(len(rows) == len(all_entries), "Row count mismatch after structured extraction")
    _require(report.get("failed", 0) == 0, f"Expected no failed rows, got report={report}")

    expected_columns = {"id", "raw_text", "confidence"} | {field.name for field in schema_fields}
    for row in rows:
        _require(expected_columns.issubset(row.keys()), "Row missing expected columns")
        _require(row.get("_meta", {}).get("status") == "ok", "Expected all rows to have status=ok")

    csv_bytes = _rows_to_csv_bytes(rows, schema_fields)
    csv_text = csv_bytes.decode("utf-8")
    parsed = list(csv.DictReader(io.StringIO(csv_text)))
    _require(len(parsed) == len(rows), "CSV row count mismatch")

    print("Workflow smoke test passed")
    print(f"Files tested: {len(file_paths)}")
    print(f"Entries: {len(all_entries)}")
    print(f"Rows: {len(rows)}")
    print(f"Run report: {report}")
    if warnings:
        print(f"Warnings: {len(warnings)}")
        for warning in warnings:
            print(f"- {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
