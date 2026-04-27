# Data Extraction Pipeline

AI-powered pipeline for converting unstructured UX research text (PDF/TXT/DOCX) into structured rows.

Current implementation covers:
- Sprint 1 (complete): extraction + segmentation
- Sprint 2 (complete): local LLM structured extraction via Ollama
- Sprint 3 (complete): validation, retry repair loop, and confidence scoring
- Sprint 4 (active): guided Streamlit workflow and CSV export

## What This Project Does

1. Reads `.txt`, `.docx`, and text-based `.pdf` files.
2. Segments raw text into entries (`id`, `raw_text`).
3. Optionally uses a local LLM (Ollama) to map entries into a user-defined schema.
4. Validates extracted rows, retries invalid outputs with repair instructions, and adds per-row confidence.

High-level flow:

`PDF/TXT/DOCX -> Text Extraction -> Entry Segmentation -> LLM Structured Extraction -> Validation/Retry -> Confidence`

## Tech Stack

- Python
- PyMuPDF (PDF extraction)
- Ollama (local model inference)

## Project Structure

- `depipeline/` - core pipeline package
- `fixtures/` - sample data and schema fixtures
- `scripts/` - helper scripts (for example, sample fixture generator)
- `tests/` - regression tests
- `sprints/` - sprint plans and status
- `docs/` - project and UI specs

## Quick Start

## 1) Install dependencies

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Windows (Git Bash):

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

## 2) Optional: prepare local LLM

```bash
ollama pull llama3.2:3b
```

## Run the Pipeline

## A) Sprint 1 mode (extract + segment only)

```bash
python -m depipeline fixtures/core/sample.txt fixtures/core/sample.pdf --sample 3
```

Example DOCX run:

```bash
python -m depipeline path/to/notes.docx --sample 3
```

## B) Sprint 2 mode (schema-driven structured extraction)

```bash
python -m depipeline \
  fixtures/core/sample.txt fixtures/core/sample.pdf \
  --schema-file fixtures/schemas/schema.typed.sample.json \
  --ollama-model llama3.2:3b \
  --validation-max-retries 2 \
  --json-out .depipeline_logs/sprint2_output.json \
  --sample 3
```

## C) Run against generated diary PDFs (bash)

```bash
python -m depipeline fixtures/generated/diary/*.pdf \
  --schema-file fixtures/schemas/schema.typed.sample.json \
  --ollama-model llama3.2:3b \
  --validation-max-retries 2 \
  --sample 3
```

## Run the Streamlit App (Sprint 4)

```bash
streamlit run app.py
```

The UI flow is:

`Upload -> Schema -> Processing -> Results -> Entry Detail`

## Common Issues

### 1) `sample.txt` or `sample.pdf` not found

If you see a file-not-found error for `sample.txt`/`sample.pdf`, use the fixture paths under `fixtures/core/` and run from the repository root:

```bash
python -m depipeline fixtures/core/sample.txt fixtures/core/sample.pdf \
  --schema-file fixtures/schemas/schema.typed.sample.json \
  --ollama-model llama3.2:3b \
  --validation-max-retries 2 \
  --sample 2
```

### 2) Unable to reach Ollama at `localhost:11434`

Start Ollama in a separate terminal before running schema-driven extraction:

```bash
ollama serve
```

Then rerun your pipeline command.

## Regression Tests

```bash
python -m unittest tests/test_extraction.py tests/test_structured_extraction.py tests/test_validation_layer.py -v
```

## Workflow Smoke Test Script

This script validates the guided workflow logic (extract -> segment -> structured extraction -> CSV export) without requiring a browser session:

```bash
python scripts/test_workflow.py
```

## Fixtures

See `fixtures/README.md` for fixture organization and additional examples.

## Current Sprint Status

See `sprints/sprints.md`.

At the moment:
- Sprint 01: complete
- Sprint 02: complete
- Sprint 03: complete
- Sprint 04: active

## Current Limitations

- OCR is not implemented yet (scanned image-only PDFs are flagged as unsupported in current pipeline mode).
- Insights dashboard is planned for Sprint 5.
