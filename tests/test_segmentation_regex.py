from __future__ import annotations

import unittest

from depipeline.segmentation import segment_entries_regex


class SegmentationRegexTests(unittest.TestCase):
    def test_splits_on_speaker_lines(self) -> None:
        text = """Alice: Hello there.
Bob: Hi!
Charlie: Good morning."""
        patterns = [r"^[A-Z][A-Za-z]+:\s+"]

        out = segment_entries_regex(text, patterns, min_entry_chars=1, merge_below_chars=0)

        self.assertEqual(len(out), 3)
        self.assertIn("Alice", out[0]["raw_text"])
        self.assertIn("Bob", out[1]["raw_text"])
        self.assertIn("Charlie", out[2]["raw_text"])


if __name__ == "__main__":
    unittest.main()
