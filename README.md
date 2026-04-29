# Data Extraction Pipeline

AI-powered pipeline for converting unstructured UX research text (PDF/TXT/DOCX) into structured rows.

Completed sprints:
- Sprint 1: extraction + segmentation
- Sprint 2: local LLM structured extraction via Ollama
- Sprint 3: validation, retry repair loop, and confidence scoring
- Sprint 4: guided Streamlit workflow and CSV export
- Sprint 5: insights screen (keyword/theme aggregation and field breakdowns)

## What This Project Does

1. Reads `.txt`, `.docx`, and text-based `.pdf` files.
2. Segments raw text into entries (`id`, `raw_text`).
3. Uses a local LLM (Ollama) to map entries into a user-defined JSON schema.
4. Validates extracted rows, retries invalid outputs with repair instructions, and adds per-row confidence scores.
5. Aggregates the results into keyword, theme, and field-breakdown insights.

High-level flow:

```
PDF/TXT/DOCX
  → Text Extraction
  → Entry Segmentation (deterministic / regex / LLM)
  → LLM Structured Extraction
  → Validation & Retry
  → Confidence Scoring
  → Insights
```

## Tech Stack

- Python 3.12
- Streamlit ≥ 1.43 (UI)
- PyMuPDF (PDF extraction)
- python-docx (DOCX extraction)
- Ollama (local model inference — no external API required)
- Altair (charts in the Insights screen)

## Project Structure

```
depipeline/        core pipeline package
  extraction.py    file → text
  segmentation.py  text → entries (deterministic / regex / LLM boundaries)
  schema.py        schema field definitions
  ollama_client.py HTTP client for Ollama
  structured_extraction.py  LLM extraction + confidence
  validation.py    field validation + retry
  insights.py      keyword / theme / field-breakdown aggregation
  cli.py           argparse CLI
app.py             Streamlit UI (single-file)
.streamlit/        Streamlit theme configuration
fixtures/          sample inputs and schema files
scripts/           fixture generator + workflow smoke test
tests/             regression tests
docs/              project spec and UI spec
sprints/           sprint plans
```

## Quick Start

### 1) Install dependencies

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

### 2) Optional: pull a local model

```bash
ollama pull llama3.2:3b
```

## Run the Streamlit App

```bash
streamlit run app.py
```

The guided UI walks through five steps:

| Step | What happens |
|------|-------------|
| **Upload** | Add `.txt`, `.pdf`, or `.docx` files |
| **Schema** | Define extraction fields, choose segmentation mode, save/load schema presets |
| **Processing** | Per-stage progress bars: extraction → segmentation → LLM → validation |
| **Results** | Summary metric cards, filterable results table, CSV export, Entry Detail modal |
| **Insights** | Keyword frequency, theme aggregation, and field-breakdown bar charts |

### Entry Detail modal

Click **Open Entry Detail →** in the Results table to open an inline modal showing the raw source text alongside all extracted fields. Use **‹ Prev** / **Next ›** to step through entries without closing the modal.

## Run the Pipeline via CLI

### Extract and segment only

```bash
python -m depipeline fixtures/core/sample.txt fixtures/core/sample.pdf --sample 3
```

### Schema-driven structured extraction

```bash
python -m depipeline \
  fixtures/core/sample.txt fixtures/core/sample.pdf \
  --schema-file fixtures/schemas/schema.typed.sample.json \
  --ollama-model llama3.2:3b \
  --validation-max-retries 2 \
  --json-out .depipeline_logs/output.json \
  --sample 3
```

## Common Issues

### `sample.txt` or `sample.pdf` not found

Run from the repository root and use the `fixtures/core/` paths explicitly:

```bash
python -m depipeline fixtures/core/sample.txt fixtures/core/sample.pdf \
  --schema-file fixtures/schemas/schema.typed.sample.json \
  --ollama-model llama3.2:3b \
  --validation-max-retries 2 \
  --sample 2
```

### Unable to reach Ollama at `localhost:11434`

Start Ollama in a separate terminal:

```bash
ollama serve
```

Then retry. In the Streamlit app, use **Test connection** in the Ollama sidebar expander to verify before running Processing.

## Tests

```bash
python -m unittest tests/test_extraction.py tests/test_structured_extraction.py tests/test_validation_layer.py -v
```

All tests (including segmentation and insights):

```bash
python -m unittest discover -s tests -v
```

Workflow smoke test (no browser required):

```bash
python scripts/test_workflow.py
```

## Fixtures

See `fixtures/README.md` for fixture organization and examples.

## Current Limitations

- OCR is not implemented (scanned image-only PDFs are flagged as unsupported).
- Insights themes use simple stem-based aggregation — semantic clustering is out of scope until Sprint 6.
