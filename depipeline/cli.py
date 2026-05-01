from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from .errors import DepipelineError
from .extraction import extract_text_with_diagnostics
from .ollama_client import OllamaClient, OllamaConfig
from .schema import load_schema_file
from .segmentation import segment_entries
from .structured_extraction import extract_structured_batch_with_validation


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="depipeline",
        description="Sprint 01 smoke-runner: extract text and segment entries.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more input files (.txt, .md/.markdown, .docx, .pdf)",
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
    parser.add_argument(
        "--schema-file",
        type=str,
        default="",
        help="Optional schema JSON file for LLM structured extraction",
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        default="llama3.2:3b",
        help="Ollama model to use when --schema-file is provided",
    )
    parser.add_argument(
        "--ollama-base-url",
        type=str,
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--ollama-timeout-seconds",
        type=int,
        default=90,
        help="Ollama request timeout in seconds (default: 90)",
    )
    parser.add_argument(
        "--ollama-temperature",
        type=float,
        default=0.0,
        help="Ollama temperature (default: 0.0 for deterministic extraction)",
    )
    parser.add_argument(
        "--raw-response-dir",
        type=str,
        default=".depipeline_logs/raw_responses",
        help="Directory where invalid model responses are saved",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Optional output path for structured extraction JSON rows",
    )
    parser.add_argument(
        "--validation-max-retries",
        type=int,
        default=2,
        help="Maximum retries per entry for validation repair (default: 2)",
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
                entry["id"] = f"{path.stem}-{path.suffix.lstrip('.')}-{entry['id']}"

            all_entries.extend(entries)
            files_processed += 1

        print(f"Files processed: {files_processed}")
        print(f"Entries produced: {len(all_entries)}")

        if args.schema_file:
            schema_fields = load_schema_file(args.schema_file)
            client = OllamaClient(
                OllamaConfig(
                    model=args.ollama_model,
                    base_url=args.ollama_base_url,
                    timeout_seconds=args.ollama_timeout_seconds,
                    temperature=args.ollama_temperature,
                )
            )

            rows, run_report = extract_structured_batch_with_validation(
                all_entries,
                schema_fields,
                client,
                raw_response_dir=args.raw_response_dir,
                show_progress=True,
                max_retries=max(0, args.validation_max_retries),
            )

            print(f"Structured rows produced: {len(rows)}")
            print(
                "Run report: "
                f"total={run_report['total_entries']}, "
                f"first_pass={run_report['valid_first_pass']}, "
                f"retried={run_report['retried']}, "
                f"failed={run_report['failed']}"
            )
            for row in rows[: max(0, args.sample)]:
                preview_fields = {field.name: row.get(field.name) for field in schema_fields}
                print(
                    f"- {row.get('id')}: {preview_fields} "
                    f"(confidence={row.get('confidence')}, status={row.get('_meta', {}).get('status')})"
                )

            if args.json_out:
                output_path = Path(args.json_out)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
                print(f"Wrote structured output: {output_path}")
        else:
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
