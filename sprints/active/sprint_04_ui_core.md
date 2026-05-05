# Sprint 04: UI Core (Streamlit)

## Goal
Deliver a clean, KISS workflow centered on inputs and outputs. Users should focus on providing files and receiving results. The pipeline still runs end-to-end, but the UI should avoid exposing internal processing details and be structured to accommodate Insights in a later sprint.

## Design Principles
- Input and output first. Users should see only what they need to provide and the results they care about.
- Reduce cognitive load. Minimize copy, hide technical stages, and avoid jargon.
- Progressively disclose. Show advanced or secondary details only when they are necessary.
- Keep actions obvious. Primary actions are clear, singular, and placed consistently.
- Favor defaults. Use sensible defaults so most users can proceed without extra decisions.

## Scope
- Streamlit app with the core screens defined in the UI spec
- File upload (PDF/TXT/MD/DOCX) and file list
- Schema builder for field definition
- Run the pipeline (internally) with simple, non-technical progress feedback
- Results table + CSV export
- Information architecture that anticipates an Insights section without adding new functionality

## Non-goals (explicitly out of scope)
- Insights functionality or dashboards (Sprint 05)
- Extra UX beyond the provided screens (no additional pages/modals/features)

## Deliverables
- A Streamlit app that follows a simple linear workflow described in [docs/ui_specs.md](../../docs/ui_specs.md):
   - Upload Screen
   - Schema Builder
   - Processing Screen (minimal status, no technical stages)
   - Results Screen (outputs-first layout that can later host Insights)
   - Entry Detail (inspect/edit + save)
- State management that persists uploaded files, schema, and results across steps
- CSV export that matches the output schema: `id, raw_text, <user_fields>, confidence`
- UI structure and copy that keep users focused on input and output (no pipeline jargon)

## Implementation Tasks
1. **App skeleton**
   - Create a single Streamlit entry point with guided, linear navigation.
   - Use `st.session_state` to hold uploaded files, schema definition, and results.

2. **Upload screen (keep it simple)**
   - Drag-and-drop upload for `.pdf`, `.txt`, `.md`, `.markdown`, and `.docx`.
   - Show a compact file list with remove controls.
   - Enable "Continue" only when at least one file is uploaded.

3. **Schema builder (only what users need)**
   - Field list + editor with name, type, and optional enum values.
   - Primary actions: "+ Add Field" and "Run Processing".

4. **Processing screen (hide internals)**
   - Run the pipeline end-to-end.
   - Show a single progress indicator or short status message (no stage breakdown).
   - Keep user-facing copy focused on “processing your files” rather than how.

5. **Results screen (focus on output)**
   - Display the results table with `id`, `confidence`, and user fields.
   - Provide "Export CSV" as the main call-to-action.
   - Provide a way to open a single row in Entry Detail.
   - Use an outputs-first layout that leaves room for future Insights content.

6. **Entry detail (lightweight editing)**
   - Show raw text and editable structured fields.
   - Persist edits back into the in-memory dataset.

## Acceptance Criteria
- A user can complete the exact workflow:
   - Upload PDF/TXT/MD/DOCX -> Continue -> Define schema -> Run Processing -> View Results -> Export CSV
- The exported CSV includes all rows and the expected columns.
- Entry Detail edits are reflected in the Results table and CSV.
- The UI does not introduce screens/components outside the UI spec.
- The UI language and layout keep users focused on inputs and outputs (no internal pipeline detail exposed).
