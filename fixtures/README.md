# Fixtures

This folder holds small sample inputs used for smoke-testing the pipeline.

- `sample.txt` is committed.
- `sample.pdf` is generated locally (binary) using the script below.

## Generate sample PDF

1. Install dependencies:

   `pip install -r requirements.txt`

2. Run:

   `python scripts/make_sample_pdf.py`

This creates `fixtures/sample.pdf`.
