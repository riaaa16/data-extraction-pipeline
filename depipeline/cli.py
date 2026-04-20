from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from .errors import DepipelineError
from .extraction import extract_text_with_diagnostics
from .segmentation import segment_entries


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="depipeline",
        description="Sprint 01 smoke-runner: extract text and segment entries.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more input files (.txt, .pdf)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=3,
        help="How many sample entries to print (default: 3)",
    )
    parser.add_argument(
        "--min-entry-chars",
        type=int,
        default=20,
        help="Minimum characters per entry to keep (default: 20)",
    )
    parser.add_argument(
        "--merge-below-chars",
        type=int,
        default=40,
        help="Merge chunks smaller than this into neighbors (default: 40)",
    )
    parser.add_argument(
        "--target-entry-chars",
        type=int,
        default=650,
        help="Target chunk size for dense text with weak/no delimiters (default: 650)",
    )

    args = parser.parse_args(argv)

    all_entries = []
    files_processed = 0

    try:
        for raw_path in args.paths:
            path = Path(raw_path)
            diagnostics = extract_text_with_diagnostics(path)
            for warning in diagnostics.warnings:
                print(f"[warn] {path.name}: {warning}")

            entries = segment_entries(
                diagnostics.text,
                min_entry_chars=args.min_entry_chars,
                merge_below_chars=args.merge_below_chars,
                target_entry_chars=args.target_entry_chars,
            )

            # Ensure IDs remain unique and deterministic across multiple files.
            for entry in entries:
                entry["id"] = f"{path.stem}-{entry['id']}"

            all_entries.extend(entries)
            files_processed += 1

        print(f"Files processed: {files_processed}")
        print(f"Entries produced: {len(all_entries)}")

        for entry in all_entries[: max(0, args.sample)]:
            raw_text = str(entry["raw_text"]).strip()
            preview = raw_text.replace("\n", " ")
            if len(preview) > 160:
                preview = preview[:157] + "..."
            print(f"- {entry['id']}: {preview}")

        return 0
    except DepipelineError as exc:
        print(f"[error] {exc}")
        return 2
