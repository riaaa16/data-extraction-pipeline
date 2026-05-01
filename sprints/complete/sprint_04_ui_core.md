# Sprint 04: UI Core (Streamlit)

## Goal
Deliver the core guided workflow UI: Upload -> Schema -> Processing -> Results, enabling users to run the pipeline end-to-end and export CSV.

## Scope
- Streamlit app with the core screens defined in the UI spec
- File upload (PDF/TXT/MD/DOCX) and file list
- Schema builder for field definition
- Run pipeline (extraction -> segmentation -> LLM -> validation)
- Results table + CSV export

## Non-goals (explicitly out of scope)
- Insights dashboard (Sprint 05)
- Semantic search / embedding-based features (Sprint 06)
- Extra UX beyond the provided screens (no additional pages/modals/features)

## Deliverables
- A Streamlit app that follows the linear workflow described in [docs/ui_specs.md](../../docs/ui_specs.md):
  - Upload Screen
  - Schema Builder
  - Processing Screen
  - Results Screen
  - Entry Detail (inspect/edit + save)
- State management that persists uploaded files, schema, and results across steps
- CSV export that matches the output schema: `id, raw_text, <user_fields>, confidence`

## Implementation Tasks
1. **App skeleton**
   - Create a single Streamlit entry point with simple step navigation (guided, linear).
   - Use `st.session_state` to hold:
     - uploaded files
     - schema definition
     - processing progress + results

2. **Upload screen**
   - Implement drag-and-drop upload supporting `.pdf`, `.txt`, and `.docx`.
   - Display uploaded file list.
   - Enable "Continue" only when at least one file is uploaded.

3. **Schema builder**
   - Implement field list + field editor:
     - name
     - type
     - enum choices (only if type is enum)
   - Add "+ Add Field" and "Run Processing" actions.

4. **Processing screen**
   - Run the pipeline with visible progress:
     - extraction
     - segmentation
     - LLM extraction
     - validation
   - Show metrics like total entries + processed entries.

5. **Results screen**
   - Display a table with key columns including `id` and `confidence`.
   - Provide "Export CSV" action.
   - Provide a way to open a single row in Entry Detail.

6. **Entry detail**
   - Show raw text and editable structured fields.
   - Persist edits back into the in-memory dataset.

## Acceptance Criteria
- A user can complete the exact workflow:
   - Upload PDF/TXT/MD/DOCX -> Continue -> Define schema -> Run Processing -> View Results -> Export CSV
- The exported CSV includes all rows and the expected columns.
- Entry Detail edits are reflected in the Results table and CSV.
- The UI does not introduce screens/components outside the UI spec.
