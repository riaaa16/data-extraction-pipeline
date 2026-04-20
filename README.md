# Data Extraction Pipeline

AI-powered pipeline for converting unstructured UX research text (PDF/TXT) into structured rows.

Current implementation covers:
- Sprint 1 (complete): extraction + segmentation
- Sprint 2 (active): local LLM structured extraction via Ollama

## What This Project Does

1. Reads `.txt` and text-based `.pdf` files.
2. Segments raw text into entries (`id`, `raw_text`).
3. Optionally uses a local LLM (Ollama) to map entries into a user-defined schema.

High-level flow:

`PDF/TXT -> Text Extraction -> Entry Segmentation -> (Optional) LLM Structured Extraction`

## Tech Stack

- Python
- PyMuPDF (PDF extraction)
- Ollama (local model inference)

## Project Structure

- `depipeline/` - core pipeline package
- `fixtures/` - sample data and schema fixtures
- `scripts/` - helper scripts (for example, sample PDF generator)
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

## B) Sprint 2 mode (schema-driven structured extraction)

```bash
python -m depipeline \
  fixtures/core/sample.txt fixtures/core/sample.pdf \
  --schema-file fixtures/schemas/schema.typed.sample.json \
  --ollama-model llama3.2:3b \
  --json-out .depipeline_logs/sprint2_output.json \
  --sample 3
```

## C) Run against generated diary PDFs (bash)

```bash
python -m depipeline fixtures/generated/diary/*.pdf \
  --schema-file fixtures/schemas/schema.typed.sample.json \
  --ollama-model llama3.2:3b \
  --sample 3
```

## Regression Tests

```bash
python -m unittest tests/test_structured_extraction.py -v
```

## Fixtures

See `fixtures/README.md` for fixture organization and additional examples.

## Current Sprint Status

See `sprints/sprints.md`.

At the moment:
- Sprint 01: complete
- Sprint 02: active

## Current Limitations

- OCR is not implemented yet (scanned image-only PDFs are flagged as unsupported in current pipeline mode).
- Full validation/retry/confidence scoring is planned for Sprint 3.
