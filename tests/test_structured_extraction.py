from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from depipeline.errors import StructuredExtractionError
from depipeline.ollama_client import OllamaResult
from depipeline.schema import load_schema_file
from depipeline.structured_extraction import extract_structured


class _FakeClient:
    def __init__(self, content: str) -> None:
        self._content = content

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> OllamaResult:
        return OllamaResult(
            content=self._content,
            model="fake-model",
            latency_ms=1,
            prompt_eval_count=1,
            eval_count=1,
            raw={"message": {"content": self._content}},
        )


class StructuredExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.schema_fields = load_schema_file(root / "fixtures" / "schema.typed.sample.json")
        self.entry = {
            "id": "entry-1",
            "raw_text": (
                "Participant: Alex\n"
                "Date: 2026-04-01\n"
                "They felt confused during onboarding.\n"
                "Suggested improvement: show progress (Step 1 of 3)."
            ),
        }

    def test_typed_fields_are_coerced(self) -> None:
        payload = {
            "participant_name": "Alex",
            "entry_date": "2026-04-01",
            "flow_step_current": "1",
            "flow_step_total": "3",
            "sentiment": "negative",
            "primary_issue": "onboarding",
            "mentions_confusion": "yes",
        }
        client = _FakeClient(json.dumps(payload))

        row = extract_structured(self.entry, self.schema_fields, client)

        self.assertEqual(row["participant_name"], "Alex")
        self.assertEqual(row["entry_date"], "2026-04-01")
        self.assertEqual(row["flow_step_current"], 1)
        self.assertEqual(row["flow_step_total"], 3)
        self.assertEqual(row["sentiment"], "negative")
        self.assertEqual(row["primary_issue"], "onboarding")
        self.assertIs(row["mentions_confusion"], True)

    def test_wrapped_json_response_is_parsed(self) -> None:
        wrapped = (
            "Here is the JSON output:\n"
            "{\n"
            "  \"participant_name\": \"Alex\",\n"
            "  \"entry_date\": \"2026-04-01\",\n"
            "  \"flow_step_current\": 1,\n"
            "  \"flow_step_total\": 3,\n"
            "  \"sentiment\": \"negative\",\n"
            "  \"primary_issue\": \"onboarding\",\n"
            "  \"mentions_confusion\": true\n"
            "}\n"
            "End"
        )
        client = _FakeClient(wrapped)

        row = extract_structured(self.entry, self.schema_fields, client)
        self.assertEqual(row["participant_name"], "Alex")
        self.assertEqual(row["flow_step_total"], 3)

    def test_invalid_json_response_is_logged(self) -> None:
        client = _FakeClient("this is not valid json")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(StructuredExtractionError):
                extract_structured(
                    self.entry,
                    self.schema_fields,
                    client,
                    raw_response_dir=tmp_dir,
                )

            saved = list(Path(tmp_dir).glob("*.txt"))
            self.assertTrue(saved, "Expected raw invalid response to be saved")


if __name__ == "__main__":
    unittest.main()
