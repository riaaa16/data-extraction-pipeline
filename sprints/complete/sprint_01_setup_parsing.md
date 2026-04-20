# Sprint 01: Setup & Parsing

## Goal
Create a reliable “input → text → entries” foundation that the LLM extraction and Streamlit UI can build on.

## Scope
- Project skeleton + dependency baseline (Python-first)
- Text extraction from `.pdf` and `.txt`
- Entry segmentation that outputs a list of `{id, raw_text}` items

## Non-goals (explicitly out of scope)
- LLM extraction, schema prompts, validation/retry, confidence scoring
- Streamlit UI screens (Upload/Schema/Processing/Results/Insights)

## Deliverables
- A documented module boundary for:
  - `extract_text(path) -> str`
  - `segment_entries(text) -> list[{id: str|int, raw_text: str}]`
- A small set of representative fixture files (at least: 1 PDF, 1 TXT)
- A smoke-test path that can run end-to-end on fixtures and prints entry count + sample entries
- Notes on known limitations (e.g., scanned PDFs / OCR not supported yet)

## Implementation Tasks
1. **Project setup**
   - Establish a minimal, clean folder layout for a modular pipeline (separate extraction/segmentation code from future UI code).
   - Add/lock core dependencies needed for Sprint 1 (PDF parser + basic data handling).

2. **Text extraction**
   - Implement PDF extraction using one primary library (`PyMuPDF` *or* `pdfplumber`) and document the choice.
   - Implement `.txt` ingestion with encoding tolerance (attempt UTF-8, fall back gracefully).
   - Normalize extracted text:
     - Consistent newlines
     - Trim excessive whitespace
     - Preserve paragraph breaks (segmentation relies on these)

3. **Entry segmentation**
   - Implement a simple, deterministic segmentation strategy suitable for UX research notes:
     - Split on blank lines into candidate chunks
     - Drop empty/very-short chunks
     - Optionally merge tiny chunks with neighbors to avoid fragments
   - Assign stable IDs (deterministic across runs for the same input ordering).

4. **Developer ergonomics**
   - Add a single command/script entry point (CLI or `python -m ...`) that:
     - Accepts one or more files
     - Runs extraction + segmentation
     - Prints summary metrics (files processed, entries produced)

## Acceptance Criteria
- Given a `.txt` file, the pipeline produces `N >= 1` entries with non-empty `raw_text`.
- Given a text-based `.pdf`, the pipeline produces `N >= 1` entries with readable text.
- Segmentation is deterministic: running twice on the same extracted text yields identical entry boundaries and IDs.
- Output shape matches the project’s baseline schema direction: each entry has `id` and `raw_text` ready for later `<user_fields>` + `confidence`.
- Failure modes are clear:
  - Unsupported file types are rejected with a helpful message.
  - Scanned PDFs are detected/flagged (no OCR in Sprint 1).
