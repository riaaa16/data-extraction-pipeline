# Fixtures

This folder holds small sample inputs used for smoke-testing the pipeline.

- `sample.txt` is committed.
- `sample.pdf` is generated locally (binary) using the script below.
- `schema.sample.json` is a basic Sprint 2 extraction schema.
- `schema.typed.sample.json` stresses number/enum/boolean coercion.

## Generate sample PDF

1. Install dependencies:

   `pip install -r requirements.txt`

2. Run:

   `python scripts/make_sample_pdf.py`

This creates `fixtures/sample.pdf`.

## Sprint 2 typed-schema smoke test

Use this command to run extraction + segmentation + LLM structuring against the typed schema:

`python -m depipeline fixtures/sample.txt fixtures/sample.pdf --schema-file fixtures/schema.typed.sample.json --ollama-model llama3.2:3b --sample 2`

## Sprint 2 regression test (fast, no Ollama required)

Run the typed extraction regression checks:

`python -m unittest tests/test_structured_extraction.py -v`
