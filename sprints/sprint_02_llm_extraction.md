# Sprint 02: LLM Extraction

## Goal
Convert segmented entries (`{id, raw_text}`) into structured rows driven by a user-defined schema using a local LLM (Ollama).

## Scope
- Local model integration via Ollama
- Schema-driven prompt construction
- Per-entry structured extraction into a consistent Python object suitable for later validation + CSV export

## Non-goals (explicitly out of scope)
- Validation/retry policies and confidence scoring (Sprint 03)
- Streamlit UI screens and user interactions (Sprint 04)
- Insights aggregation (Sprint 05)

## Deliverables
- An Ollama client wrapper (configurable model name, host/port, timeout)
- A schema representation used for prompting (field name, type, enum choices)
- A prompt builder that takes `(schema, raw_text)` and requests strictly-structured output
- An extractor that returns:
  - `id`
  - `raw_text`
  - `<user_fields>` (per schema)
  - (optional) model metadata like `model`, `latency_ms`, `tokens` if available
- A runnable smoke test against the Sprint 01 fixtures that produces structured rows (even if imperfect)

## Implementation Tasks
1. **Define schema contract**
   - Decide a minimal schema structure that matches the UI Schema Builder later (name, type, optional enum list).
   - Supported field types for MVP: `string`, `number`, `boolean`, `enum`.

2. **Ollama integration**
   - Implement an adapter that can call Ollama deterministically (temperature defaults low).
   - Centralize configuration (model name, base URL, timeout).
   - Provide a clear error when Ollama is not running / model not pulled.

3. **Prompting strategy**
   - Build a schema-driven prompt that:
     - Uses the schema to describe each field
     - Instructs the model to only use information present in `raw_text`
     - Requests a strict JSON object output (no prose)
   - Include guidance for missing fields (use `null` rather than guessing).

4. **Extraction pipeline integration**
   - Implement `extract_structured(entry, schema) -> dict`.
   - Batch over entries with basic progress reporting (stdout) for later UI reuse.
   - Store intermediate results in-memory; persistence can remain optional.

5. **Quality checks (lightweight)**
   - Add a minimal “JSON parse” guard:
     - Extract JSON substring if the model wraps it
     - Fail clearly if output cannot be parsed as JSON
   - Defer full validation + retries to Sprint 03.

## Acceptance Criteria
- With Ollama running and a supported model available, the system can process `N >= 1` entries and produce a structured dict per entry.
- The extractor obeys the schema shape: output includes exactly the schema fields (plus `id`, `raw_text`).
- Missing/unknown values are represented as `null` (not hallucinated).
- Failures are actionable:
  - If Ollama is unreachable, the error message points to starting Ollama / pulling the model.
  - If model output is not valid JSON, the failure is surfaced with the raw model response saved/logged for debugging.
