from __future__ import annotations

import json
import unittest

from depipeline.errors import DepipelineError
from depipeline.ollama_client import OllamaResult
from depipeline.segmentation import segment_entries_llm_boundaries


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


class SegmentationLLMTests(unittest.TestCase):
    def test_parses_object_with_line_ranges(self) -> None:
        payload = {
            "entries": [
                {"start_line": 1, "end_line": 2},
                {"start_line": 3, "end_line": 3},
            ]
        }
        client = _FakeClient(json.dumps(payload))

        out = segment_entries_llm_boundaries("Line A\nLine B\nLine C", client, min_entry_chars=1)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["id"], 1)
        self.assertIn("Line A", str(out[0]["raw_text"]))

    def test_parses_list_of_ranges(self) -> None:
        client = _FakeClient(json.dumps([
            {"start_line": 1, "end_line": 1},
            {"start_line": 2, "end_line": 3},
        ]))
        out = segment_entries_llm_boundaries("One\nTwo\nThree", client, min_entry_chars=1)
        self.assertEqual([e["raw_text"] for e in out], ["One", "Two\nThree"])

    def test_invalid_json_raises(self) -> None:
        client = _FakeClient("not json")
        with self.assertRaises(DepipelineError):
            segment_entries_llm_boundaries("hello", client)


if __name__ == "__main__":
    unittest.main()
