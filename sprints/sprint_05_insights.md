# Sprint 05: Insights

## Goal
Provide basic aggregated insights (themes/keywords and summary counts) over the structured dataset.

## Scope
- Keyword extraction and simple theme aggregation
- Summary stats grouped by key fields (when present in schema)
- Insights display in the existing “Insights” screen defined in the UI spec

## Non-goals (explicitly out of scope)
- Advanced topic modeling or semantic clustering beyond basic aggregation
- Full semantic search (Sprint 06)
- Expanding UI beyond the specified Insights screen

## Deliverables
- An insights computation module that takes the extracted dataset and produces:
  - keyword list(s) with counts
  - theme labels with counts (simple, explainable approach)
  - summary counts by selected fields (e.g., platform)
- An “Insights” view that displays:
  - Themes section
  - Field breakdown section(s) (only for fields that exist)

## Implementation Tasks
1. **Define insights inputs/outputs**
   - Input: the final structured rows with `raw_text` and schema fields.
   - Output: a single insights object used by the UI.

2. **Keyword extraction**
   - Implement a lightweight keyword approach (no heavy infra):
     - tokenization + stopword removal + frequency counts, or
     - TF-IDF over `raw_text` chunks
   - Ensure results are stable and fast on typical UX datasets.

3. **Theme aggregation**
   - Implement a minimal theme strategy:
     - Option A: LLM-assisted labeling over top keywords (small batch)
     - Option B: rule-based grouping by keyword stems
   - Keep it deterministic where feasible and document the tradeoffs.

4. **Insights screen**
   - Add an Insights view that matches [docs/ui_specs.md](../docs/ui_specs.md):
     - “Themes: theme (count)”
     - “Platform / other field: value (count)”

## Acceptance Criteria
- Running insights on a processed dataset produces:
  - a non-empty keyword list (when there is non-empty text)
  - at least one theme bucket with counts
- The Insights screen renders without errors and uses the existing UI spec layout.
- Insights results are reproducible on the same input dataset.
