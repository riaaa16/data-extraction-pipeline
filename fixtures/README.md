# Fixtures

This folder holds small sample inputs used for smoke-testing the pipeline.

The pipeline accepts `.txt`, `.md`/`.markdown`, `.docx`, and `.pdf` inputs.

## Layout

- `core/`
   - `sample.txt` (generated baseline text fixture)
   - `sample.docx` (generated baseline DOCX fixture)
   - `sample.pdf` (generated baseline PDF fixture)
- `schemas/`
   - `schema.sample.json` (basic Sprint 2 extraction schema)
   - `schema.typed.sample.json` (number/enum/boolean stress schema)
- `generated/`
   - `diary/` (bulk generated PDFs for realism/coverage)

## Generate core sample fixtures

1. Install dependencies:

   `pip install -r requirements.txt`

2. Run:

   `python scripts/make_sample_pdf.py`

This creates:

- `fixtures/core/sample.txt`
- `fixtures/core/sample.docx`
- `fixtures/core/sample.pdf`

## Sprint 2 typed-schema smoke test

Use this command to run extraction + segmentation + LLM structuring against the typed schema:

`python -m depipeline fixtures/core/sample.txt fixtures/core/sample.pdf --schema-file fixtures/schemas/schema.typed.sample.json --ollama-model llama3.2:3b --sample 2`

To run against the generated diary batch in bash:

`python -m depipeline fixtures/generated/diary/*.pdf --schema-file fixtures/schemas/schema.typed.sample.json --ollama-model llama3.2:3b --sample 3`

## Sprint 2 regression test (fast, no Ollama required)

Run the typed extraction regression checks:

`python -m unittest tests/test_extraction.py tests/test_structured_extraction.py tests/test_validation_layer.py -v`

Run the workflow smoke test script (no browser, no Ollama required):

`python scripts/test_workflow.py`
