# Data Extraction Pipeline

AI-powered pipeline for converting unstructured UX research text (PDF/TXT/DOCX) into structured, queryable rows.

## What It Does

1. Reads `.txt`, `.docx`, and text-based `.pdf` files.
2. Segments raw text into discrete entries using deterministic heuristics, user-defined regex patterns, or an LLM.
3. Uses a local LLM (via [Ollama](https://ollama.com)) to map each entry to a user-defined JSON schema.
4. Validates extracted rows, retries invalid outputs with repair instructions, and attaches per-row confidence scores.
5. Surfaces keyword frequency, theme aggregation, and field-breakdown charts in an Insights screen.

```
PDF / TXT / DOCX
  → Text Extraction
  → Entry Segmentation  (deterministic / regex / LLM)
  → LLM Structured Extraction
  → Validation & Retry
  → Confidence Scoring
  → Results + Insights
```

## Tech Stack

| Dependency | Purpose |
|---|---|
| Python 3.12 | Runtime |
| Streamlit ≥ 1.43 | Web UI |
| Ollama | Local LLM inference (no external API) |
| PyMuPDF | PDF text extraction |
| python-docx | DOCX text extraction |
| Altair | Charts in the Insights screen |

## Project Structure

```
depipeline/
  extraction.py          file → plain text
  segmentation.py        text → entries (deterministic / regex / LLM)
  schema.py              schema field definitions and loading
  ollama_client.py       HTTP client for Ollama
  structured_extraction.py  LLM extraction + confidence scoring
  validation.py          field validation + retry-repair loop
  insights.py            keyword / theme / field-breakdown aggregation
  cli.py                 argparse CLI entry point
app.py                   Streamlit UI (single file)
.streamlit/              Theme configuration
fixtures/                Sample inputs and schema files
scripts/                 Fixture generator + workflow smoke test
tests/                   Regression tests
```

## Quick Start

### 1. Install dependencies

**Windows — PowerShell:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Windows — Git Bash / macOS / Linux:**
```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

### 2. Pull a local model (one-time)

```bash
ollama pull llama3.2:3b
```

Any model available in your local Ollama installation works. Larger models are slower but more accurate.

### 3. Start Ollama

```bash
ollama serve
```

### 4. Launch the app

```bash
streamlit run app.py
```

---

## Guided UI Walkthrough

The app is a five-step wizard. Use the sidebar or the top stepper to navigate between completed steps.

### Step 1 — Upload

Drag and drop one or more `.txt`, `.pdf`, or `.docx` files. Multiple files are processed in order and their entries are merged into a single dataset. Remove individual files with the ✕ button before proceeding.

### Step 2 — Schema

Define the fields you want to extract from each entry.

| Field option | Description |
|---|---|
| **Name** | The key that will appear as a column in results |
| **Type** | `string`, `number`, `boolean`, or `enum` |
| **Description** | Optional hint sent to the LLM to guide extraction |
| **Enum values** | Comma-separated list of allowed values (only for `enum` type) |

**Schema presets** — Save the current schema under a name and reload it in future sessions via the *Saved Schemas* expander.

**Entry Separation** — Choose how the raw text is split into individual entries before LLM extraction:

| Mode | When to use |
|---|---|
| **Deterministic** | Default. Heuristic block-detection; works well for most structured documents. |
| **Regex** | Supply one or more Python regex patterns that mark the *start* of each entry (e.g. speaker labels in interview transcripts). Includes built-in presets for common transcript formats and an **LLM Regex Helper** that suggests a pattern from a sample heading. |
| **LLM** | The model identifies entry boundaries from context. Best for documents with no consistent structural markers. Provide a dataset description for better results. |

### Step 3 — Processing

Four-stage progress bars track the pipeline in real time:

1. **Text Extraction** — converts uploaded files to plain text
2. **Segmentation** — splits text into entries
3. **LLM Extraction** — sends each entry to Ollama with your schema
4. **Validation** — checks types and retries malformed responses

A summary metric card shows total entries, first-pass valid count, retries, and failures once done.

### Step 4 — Results

| Feature | Details |
|---|---|
| **Metric cards** | Total entries, first-pass valid, retried, failed |
| **Filter bar** | Searches across all rows and all fields (including raw source text). Shows match count when active. Hover the search bar for the full list of searchable fields. |
| **Table** | Click any row to pre-select it |
| **Entry Detail** | Click **Open Entry Detail →** (or select from the dropdown) to open a modal with the raw source text and all extracted fields. Use **‹ Prev** / **Next ›** to step through entries without closing. |
| **CSV export** | Downloads all rows (not just the visible preview) as `depipeline_results.csv` |

### Step 5 — Insights

Aggregated views over the full dataset:

- **Themes** — frequency bar chart of recurring theme labels extracted from `raw_text`
- **Keywords** — top-N keyword frequency across all entries
- **Field breakdowns** — value-count bar chart for each low-cardinality field (enum, boolean)

---

## Ollama Settings (Sidebar)

Expand the **Ollama** panel in the sidebar to adjust:

| Setting | Default | Notes |
|---|---|---|
| Model | `llama3.2:3b` | Any model pulled locally |
| Base URL | `http://localhost:11434` | Change if Ollama runs on a different host/port |
| Timeout (minutes) | `3` | Increase for slow hardware or large entries |
| Validation retries | `2` | Number of repair attempts per malformed extraction |

Click **Test connection** to verify Ollama is reachable before running Processing.

---

## CLI Usage

The CLI uses deterministic segmentation only; for LLM-based segmentation use the Streamlit app.

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

**All CLI flags:**

| Flag | Default | Description |
|---|---|---|
| `--sample N` | `3` | Number of sample entries printed to stdout |
| `--min-entry-chars N` | `20` | Drop entries shorter than N characters |
| `--merge-below-chars N` | `40` | Merge chunks shorter than N into neighbours |
| `--target-entry-chars N` | `650` | Target size for dense-text sentence-window splitting |
| `--schema-file PATH` | — | JSON schema file; enables LLM extraction |
| `--ollama-model NAME` | `llama3.2:3b` | Model to use for extraction |
| `--ollama-base-url URL` | `http://localhost:11434` | Ollama server URL |
| `--ollama-timeout-seconds N` | `90` | Per-request timeout |
| `--ollama-temperature F` | `0.0` | Sampling temperature (0 = deterministic) |
| `--validation-max-retries N` | `2` | Retry attempts for invalid responses |
| `--raw-response-dir PATH` | `.depipeline_logs/raw_responses` | Where to save invalid model responses |
| `--json-out PATH` | — | Write structured rows to a JSON file |

---

## Tests

Run the full test suite:

```bash
python -m unittest discover -s tests -v
```

Specific test modules:

```bash
python -m unittest tests/test_extraction.py tests/test_structured_extraction.py tests/test_validation_layer.py -v
```

Workflow smoke test (no browser, no Ollama required):

```bash
python scripts/test_workflow.py
```

---

## Common Issues

### Unable to reach Ollama at `localhost:11434`

Start Ollama in a separate terminal:

```bash
ollama serve
```

Then use **Test connection** in the sidebar to verify before running Processing.

### LLM mode produces too many entries

Switch to **Regex** or **Deterministic** mode in the Schema step, or add a dataset description under LLM mode to give the model context about what one entry looks like.

### Scanned / image-only PDFs return no text

OCR is not implemented. Only PDFs with embedded text layers are supported. The app will flag unsupported files with a warning.

### `sample.txt` or fixture not found

Run all commands from the repository root directory.

---

## Fixtures

See `fixtures/README.md` for fixture organisation and available sample files.
