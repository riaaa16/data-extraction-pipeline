# Sprint 03: Validation Layer

## Goal
Increase reliability by validating extracted rows, retrying when outputs are invalid, and attaching a confidence score per row.

## Scope
- JSON/schema validation of LLM outputs
- Retry logic with controlled prompt repair
- Confidence scoring strategy (simple, explainable)

## Non-goals (explicitly out of scope)
- Streamlit UI (Sprint 04)
- Insights aggregation (Sprint 05)
- Advanced semantic search (Sprint 06)

## Deliverables
- A validator that checks extracted rows against the schema:
  - Required keys present
  - Type checks (`string/number/boolean/enum`)
  - Enum membership enforcement
- A retry controller:
  - Max attempts
  - “repair prompt” that includes validation errors
  - Backoff / stop conditions
- A confidence score per row (0–1) plus optional reason codes
- A structured “run report” summary:
  - total entries
  - valid on first pass
  - retried
  - failed

## Implementation Tasks
1. **Choose validation mechanism**
   - Implement validation with a lightweight approach:
     - Either `pydantic` models built from the schema, or
     - A custom validator that returns a list of errors per row
   - Keep the validation errors machine-usable (field name + message).

2. **Integrate validation into extraction loop**
   - After Sprint 02 extraction, validate each row.
   - If invalid, attempt a retry with:
     - The original `raw_text`
     - The schema
     - The list of validation errors

3. **Retry policy**
   - Set a small max retry count (e.g., 2–3) to avoid runaway costs/time.
   - Stop retrying if:
     - Output parses but still violates constraints in the same way repeatedly, or
     - The model returns empty/irrelevant content.

4. **Confidence scoring**
   - Define a simple confidence calculation that correlates with quality:
     - Start at 1.0
     - Subtract penalties for retries, missing fields, type coercions
     - Clamp to [0, 1]
   - Record confidence inputs for transparency.

5. **Result normalization**
   - Ensure final row shape matches the project output schema direction:
     - `id`, `raw_text`, `<user_fields>`, `confidence`

## Acceptance Criteria
- Invalid extracted rows are detected reliably (type/enum/key checks).
- For a representative fixture run:
  - Some invalid outputs trigger retries
  - Final outputs are either valid rows or explicitly marked failed
- Each successful row includes `confidence` in [0, 1].
- Retry attempts are bounded and reported in a run summary.
