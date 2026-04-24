from __future__ import annotations

import json
import unittest
from pathlib import Path

from depipeline.ollama_client import OllamaResult
from depipeline.schema import load_schema_file
from depipeline.structured_extraction import extract_structured_batch_with_validation
from depipeline.validation import validate_model_object


class _SequencedFakeClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self._index = 0

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> OllamaResult:
        idx = min(self._index, len(self._responses) - 1)
        self._index += 1
        content = self._responses[idx]
        return OllamaResult(
            content=content,
            model="fake-model",
            latency_ms=1,
            prompt_eval_count=1,
            eval_count=1,
            raw={"message": {"content": content}},
        )


class ValidationLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.schema_fields = load_schema_file(root / "fixtures" / "schemas" / "schema.typed.sample.json")
        self.entry = {
            "id": "entry-1",
            "raw_text": (
                "Participant: Alex\n"
                "Date: 2026-04-01\n"
                "Suggested improvement: show progress (Step 1 of 3)."
            ),
        }

    def test_validator_detects_missing_and_extra_keys(self) -> None:
        model_obj = {
            "participant_name": "Alex",
            "entry_date": "2026-04-01",
            "flow_step_current": 1,
            "flow_step_total": 3,
            "sentiment": "negative",
            "primary_issue": "onboarding",
            "unexpected": "value",
        }

        result = validate_model_object(model_obj, self.schema_fields)

        self.assertFalse(result.valid)
        codes = {issue.code for issue in result.issues}
        self.assertIn("missing_key", codes)
        self.assertIn("extra_key", codes)

    def test_retry_then_success_updates_report_and_confidence(self) -> None:
        invalid = json.dumps(
            {
                "participant_name": "Alex",
                "entry_date": "2026-04-01",
                "flow_step_current": "abc",
                "flow_step_total": "3",
                "sentiment": "negative",
                "primary_issue": "onboarding",
                "mentions_confusion": "yes",
            }
        )

        valid = json.dumps(
            {
                "participant_name": "Alex",
                "entry_date": "2026-04-01",
                "flow_step_current": 1,
                "flow_step_total": 3,
                "sentiment": "negative",
                "primary_issue": "onboarding",
                "mentions_confusion": True,
            }
        )

        client = _SequencedFakeClient([invalid, valid])

        rows, report = extract_structured_batch_with_validation(
            [self.entry],
            self.schema_fields,
            client,
            show_progress=False,
            max_retries=2,
        )

        self.assertEqual(report["total_entries"], 1)
        self.assertEqual(report["valid_first_pass"], 0)
        self.assertEqual(report["retried"], 1)
        self.assertEqual(report["failed"], 0)

        row = rows[0]
        self.assertEqual(row["_meta"]["status"], "ok")
        self.assertEqual(row["_meta"]["retries"], 1)
        self.assertGreater(row["confidence"], 0.0)
        self.assertLess(row["confidence"], 1.0)

    def test_repeated_invalid_output_becomes_failed_row(self) -> None:
        invalid = json.dumps(
            {
                "participant_name": "Alex",
                "entry_date": "2026-04-01",
                "flow_step_current": "not-a-number",
                "flow_step_total": "not-a-number",
                "sentiment": "bad-value",
                "primary_issue": "unknown-value",
                "mentions_confusion": "maybe",
            }
        )
        client = _SequencedFakeClient([invalid, invalid, invalid])

        rows, report = extract_structured_batch_with_validation(
            [self.entry],
            self.schema_fields,
            client,
            show_progress=False,
            max_retries=2,
        )

        self.assertEqual(report["total_entries"], 1)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["retried"], 1)

        row = rows[0]
        self.assertEqual(row["_meta"]["status"], "failed")
        self.assertEqual(row["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
