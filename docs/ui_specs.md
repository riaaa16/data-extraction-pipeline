# Streamlit UI Specs — Sprint 5

## Overview & Design Philosophy

The app uses a single-page, sidebar-driven layout. The left sidebar holds persistent navigation and global Ollama config. The main content area renders the active step. A progress stepper at the top of the main area always shows where the user is and what is complete.

Primary design goals:
- **Reduce cognitive load**: expose only what is needed for the current step.
- **Clear progress feedback**: per-stage labelled progress bars during processing.
- **Recoverability**: jump back to any completed step without losing state.
- **Minimal visual noise**: `st.container` cards, subtle dividers, muted secondary text.

### Colour palette

Set via `.streamlit/config.toml` (applies automatically to all Streamlit components):

| Role | Value |
|------|-------|
| Background | `#F8F9FA` |
| Card / container surface | `#FFFFFF` |
| Primary accent | `#4F6CF7` (indigo) |
| Success | `#22C55E` |
| Warning | `#F59E0B` |
| Error | `#EF4444` |
| Muted text | `#6B7280` |

Additional styles injected via `st.markdown` in `main()`:
- Monospace font (`JetBrains Mono`, Fira Mono, Consolas) applied to all `textarea` elements.
- Left-aligned sidebar nav buttons.
- Radio group options left-aligned.

---

## Global Layout

```
┌──────────────────┬──────────────────────────────────────────────┐
│   SIDEBAR        │  MAIN CONTENT AREA                           │
│                  │                                              │
│  App logo/title  │  ── Step Stepper ───────────────────────    │
│                  │   Upload  Schema  Process  Results  Insights  │
│  ── Navigation   │                                              │
│  Upload      ●   │  <active step content>                       │
│  Schema      ○   │                                              │
│  Process     ○   │                                              │
│  Results     ○   │                                              │
│  Insights    ○   │                                              │
│                  │                                              │
│  ── Ollama ────  │                                              │
│  Model           │                                              │
│  Base URL        │                                              │
│  Timeout         │                                              │
│  Retries         │                                              │
│  [Test conn]     │                                              │
└──────────────────┴──────────────────────────────────────────────┘
```

### Sidebar — always visible

**App header**
- Small indigo square icon + "DE Pipeline" (semibold) + "Data Extraction Pipeline" subtitle (muted 12px).

**Navigation**
- Five `st.button` labels: Upload, Schema, Process, Results, Insights.
- Status icon prefix: `✅` completed · `●` active · `○` future.
- Future steps are disabled (`disabled=True`).
- Clicking a completed or active step navigates without resetting state.

**Ollama Configuration** (`st.expander("Ollama", expanded=False)`)
- `st.text_input` — Model (default: `llama3.2:3b`)
- `st.text_input` — Base URL (default: `http://localhost:11434`)
- `st.number_input` — Timeout in minutes (default: 3, min: 1, max: 30)
- `st.number_input` — Validation max retries (default: 2, min: 0, max: 10)
- `st.button("Test connection")` — lightweight GET to `/api/tags`; shows `st.success` / `st.error` inline.

---

## Step Stepper Component

HTML/CSS block rendered at the top of the main area on every screen via `st.markdown(..., unsafe_allow_html=True)`.

- Completed steps: green dot.
- Active step: indigo dot.
- Future steps: grey dot.
- Completed/active steps render as `<a href='?nav=<key>'>` links for direct navigation.

---

## Screen 1 — Upload

### Purpose
Collect one or more files (.txt, .pdf, .docx) to process.

### Layout

```
┌─────────────────────────────────────────────────┐
│  Upload Files                                   │
│  Add the documents you want to extract from.   │
│                                                 │
│  [ Drag & drop files here (file uploader) ]    │
│                                                 │
│  Uploaded files  (2 files · 204 KB total)       │
│  ┌──────────────────────────────────────────┐  │
│  │ 📄 interview_batch_1.pdf    120 KB    ✕  │  │
│  │ 📄 responses_march.docx      84 KB    ✕  │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│                      [ Continue → Schema ]      │
└─────────────────────────────────────────────────┘
```

### Components

**File uploader** — `st.file_uploader(accept_multiple_files=True, type=["txt","pdf","docx"])`.

**Uploaded file list**
- Each row: `st.columns([6, 2, 1], vertical_alignment="center")` — filename + muted size caption + ✕ remove button.
- Muted count line above: "N files · X KB total."
- Only shown when at least one file is uploaded; otherwise `st.info` prompt.

**Continue button** — `st.button("Continue → Schema", type="primary", use_container_width=True)`, right-aligned via `st.columns([6, 2])`, disabled when no files are uploaded.

### Session State
- `uploaded_files`: list of `{name, bytes, size}` dicts — populated on first upload, persists across all steps.

---

## Screen 2 — Schema

### Purpose
Define extraction fields, choose segmentation mode, and save/load schema presets.

### Components

**Field cards** — each field rendered inside `st.container(border=True)` with a 4-column row:
- `Name` (text input) · `Type` (selectbox: string / number / boolean / enum) · `Description` (text input) · `Remove` button.
- When `type == "enum"`: full-width `st.text_input("Enum values (comma-separated)")` rendered below.

**Add Field button** — `st.button("+ Add Field")`, always visible below the field list.

**Saved Schemas** (`st.expander("Saved Schemas", expanded=False)`)
- Save: name input + 💾 Save button → writes JSON to `.depipeline_logs/saved_schemas/<name>.json`.
- Load: selectbox of saved schema files + 📂 Load button → populates `schema_fields` and reruns.

**Entry Separation** (`st.expander("Entry Separation", expanded=True)`)
- `st.radio("Mode", ["Deterministic", "Regex", "LLM"], horizontal=True)`.
- *Deterministic*: `st.info` message only.
- *Regex*: `st.text_area` (one pattern per line, monospace) + preset selectbox + Apply button + LLM Regex Helper sub-expander.
- *LLM*: dataset description `st.text_area` + info box.

**Navigation**
- Left: `st.button("← Back")` → Upload.
- Right: `st.button("Run Processing →", type="primary")` → validates fields, sets `schema_ready = True`, navigates to Processing.

---

## Screen 3 — Processing

### Purpose
Run the full pipeline with per-stage progress feedback.

### Layout (during run)

```
┌──────────────────────────────────────────────────────┐
│  Processing                                          │
│  Running your pipeline. This may take a few minutes.│
│                                                      │
│  Stage Progress                                      │
│  1 — Text Extraction    [████████████] 100%         │
│  2 — Segmentation       [████████░░░░]  67%         │
│  3 — LLM Extraction     [░░░░░░░░░░░░]   0%         │
│  4 — Validation         [░░░░░░░░░░░░]   0%         │
│                                                      │
│  Files: 2/3 | Entries: 14 | LLM: 4/14              │
└──────────────────────────────────────────────────────┘
```

### Layout (after completion)

```
│  ✅ Processing complete.                             │
│  ┌────────┐ ┌────────────┐ ┌────────┐ ┌────────┐   │
│  │ Total  │ │First-pass  │ │Retried │ │ Failed │   │
│  │  120   │ │   110      │ │   10   │ │    0   │   │
│  └────────┘ └────────────┘ └────────┘ └────────┘   │
│                                                      │
│  [ ← Back to Schema ]       [ Continue → Results ]  │
```

### Components

**Stage progress bars** — four sequentially labelled `st.progress` bars: `1 — Text Extraction`, `2 — Segmentation`, `3 — LLM Extraction`, `4 — Validation`. Updated via a `progress_callback` passed to `extract_structured_batch_with_validation`.

**Live metrics** — `st.empty()` placeholder updated with file/entry/LLM counts during the run.

**Completion metrics** — `st.columns(4)` with `st.metric` for Total, First-pass valid, Retried, Failed.

**Error handling** — fatal `DepipelineError` shown via `st.error`; if Ollama is unreachable a "Restart process" button appears to clear run state.

**Navigation**
- `st.button("← Back to Schema")` — always enabled.
- `st.button("Continue → Results", type="primary")` — disabled if `pipeline_error` is set.

---

## Screen 4 — Results

### Purpose
Review extracted entries, filter, export to CSV, and inspect individual entries.

### Layout

```
┌──────────────────────────────────────────────────────┐
│  Results                                             │
│                                                      │
│  ┌────────┐ ┌────────────┐ ┌────────┐ ┌────────┐   │
│  │ Total  │ │First-pass  │ │Retried │ │ Failed │   │
│  │  120   │ │   110      │ │   10   │ │    0   │   │
│  └────────┘ └────────────┘ └────────┘ └────────┘   │
│                                                      │
│  ▸ Warnings (2)  (collapsed expander)               │
│                                                      │
│  [ 🔍 Type to filter by any field…         ]        │
│  Showing 25 of 120 rows · select a row then click…  │
│                                                      │
│  ID  │ participant_name │ sentiment │ confidence     │
│  001 │ Alex             │ negative  │ 0.82           │
│  002 │ Sam              │ neutral   │ 0.77           │
│                                                      │
│  [ 📥 Export CSV ]                                  │
│                                                      │
│  Select entry [ 001 ▾ ]  [ Open Entry Detail → ]   │
│                                                      │
│  [ ← Back to Processing ]   [ Continue → Insights ] │
└──────────────────────────────────────────────────────┘
```

### Components

**Summary metrics** — `st.columns(4)` with `st.metric`: Total entries, First-pass valid, Retried, Failed. Failed metric shows a delta label if `> 0`.

**Warnings** — `st.expander(f"Warnings ({n})", expanded=False)`, only rendered when warnings exist.

**Filter bar** — `st.text_input` (collapsed label, placeholder "🔍 Type to filter by any field…"). Filters `preview_rows` client-side (case-insensitive match against any column value).

**Results table** — `st.dataframe(use_container_width=True, on_select="rerun", selection_mode="single-row")`. Selecting a row sets `table_selection_id`; this takes precedence over the selectbox.

**Export CSV** — `st.download_button("📥 Export CSV")`, includes `id + raw_text + schema fields + confidence`.

**Entry selector + open** — `st.selectbox("Select entry")` synced with table selection; `st.button("Open Entry Detail →")` sets `show_entry_detail = True` and reruns.

**Navigation**
- `st.button("← Back to Processing")`
- `st.button("Continue → Insights", type="primary")`

### Session State
- `results_filter`: str — current filter query.
- `selected_row_id`: str — currently selected entry ID.
- `show_entry_detail`: bool — controls whether the Entry Detail dialog is open.

---

## Screen 4b — Entry Detail (Modal Dialog)

Rendered as `@st.dialog("Entry Detail", width="large")` called at the bottom of the Results screen when `show_entry_detail` is True.

### Layout

```
┌──────────────────────────────────────────────────────┐
│  Entry Detail                                    [✕] │
│                                                      │
│  Entry 3 of 120          [ ‹ Prev ]  [ Next › ]     │
│                                                      │
│  Confidence  0.82                                    │
│                                                      │
│  Raw Text                                            │
│  ┌──────────────────────────────────────────────┐   │
│  │ Participant: Alex                            │   │
│  │ …                                            │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  participant_name  [ Alex        ]                   │
│  sentiment         [ negative ▾ ]                   │
│                                                      │
│  ────────────────────────────────────────────────── │
│                                   [ Close ]          │
└──────────────────────────────────────────────────────┘
```

### Components

**Navigation row** — `st.columns([4, 1, 1])`: entry N of total caption + `‹ Prev` / `Next ›` buttons (disabled at boundaries). Clicking updates `selected_row_id` and calls `st.rerun()`.

**Confidence metric** — `st.metric("Confidence", f"{conf:.2f}")`, read-only.

**Raw Text** — `st.text_area(height=180, disabled=True)` with monospace font (applied via global CSS).

**Field editors** — type-aware, all `disabled=True` (read-only view):
- `string` → `st.text_input`
- `number` → `st.number_input`
- `boolean` → `st.checkbox`
- `enum` → `st.selectbox`

**Footer** — `st.divider()` + `st.button("Close")` (right-aligned). Clicking sets `show_entry_detail = False` and calls `st.rerun()` to dismiss the dialog.

### Notes
- The dialog uses `width="large"` from Streamlit's native `@st.dialog` decorator — no manual CSS width overrides.
- There is no inner `st.container(height=...)` wrapper; the dialog scrolls naturally if content overflows.

---

## Screen 5 — Insights

### Purpose
Aggregated themes, keyword frequencies, and field-breakdown charts over the processed dataset.

### Layout

```
┌──────────────────────────────────────────────────────┐
│  Insights                                            │
│  Aggregated themes and simple counts…               │
│                                                      │
│  ┌─ Themes ──────────────────────────────────────┐  │
│  │  [horizontal bar chart — theme vs count]      │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ Keywords ────────────────────────────────────┐  │
│  │  [horizontal bar chart — keyword vs count]    │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  Field breakdowns                                    │
│  ┌─ sentiment ───────────────────────────────────┐  │
│  │  [horizontal bar chart — value vs count]      │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  [ ← Back to Results ]                              │
└──────────────────────────────────────────────────────┘
```

### Components

**Themes** — `st.container(border=True)` with an Altair horizontal bar chart (`mark_bar`, `x=count:Q`, `y=theme:N sort=-x`). Falls back to `st.caption` if no themes.

**Keywords** — same pattern as Themes.

**Field breakdowns** — one `st.container(border=True)` per low-cardinality schema field that has breakdown data. Only rendered if `insights.field_breakdowns` is non-empty.

**Empty / no-text states** — `st.info` messages if rows are empty or `raw_text` is blank for all rows.

**Navigation** — `st.button("← Back to Results")`.

---

## CSS Injection Reference (`main()`)

```css
/* Layout */
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* Radio groups: left-align options */
div[data-testid="stRadio"] [role="radiogroup"] { justify-content: flex-start; }

/* Monospace font for all textareas (raw text, regex patterns) */
div[data-testid="stTextArea"] textarea {
    font-family: "JetBrains Mono", "Fira Mono", "Consolas", monospace;
    font-size: 13px;
}

/* Left-align sidebar nav buttons */
section[data-testid="stSidebar"] div[data-testid="stButton"] button {
    text-align: left;
    justify-content: flex-start;
}
```

---

## Session State Master Reference

| Key | Type | Set by | Used by |
|-----|------|--------|---------|
| `step` | str | Navigation | All screens |
| `session_id` | str | Init | Processing (upload path) |
| `uploaded_files` | list[dict] | Upload | All screens |
| `schema_fields` | list[dict] | Schema | Process, Results |
| `schema_field_objects` | list[SchemaField] | Schema/Process | Process, Results, Insights |
| `schema_ready` | bool | Schema | Processing |
| `segmentation_mode` | str | Schema | Processing |
| `segmentation_regex_patterns` | str | Schema | Processing |
| `dataset_description` | str | Schema | Processing |
| `ollama_model` | str | Sidebar | Processing, Schema |
| `ollama_base_url` | str | Sidebar | Processing, Schema |
| `ollama_timeout_minutes` | int | Sidebar | Processing, Schema |
| `validation_max_retries` | int | Sidebar | Processing |
| `processing_done` | bool | Processing | Processing |
| `pipeline_error` | str | Processing | Processing, Insights |
| `entries` | list[dict] | Processing | (reference) |
| `rows` | list[dict] | Processing | Results, Insights |
| `run_report` | dict | Processing | Processing, Results |
| `processing_warnings` | list[str] | Processing | Results |
| `insights` | InsightsResult | Processing | Insights |
| `selected_row_id` | str | Results | Results, Entry Detail |
| `show_entry_detail` | bool | Results | Results |
| `results_filter` | str | Results | Results |
| `sample_preview_count` | int | Init | Results |
| `regex_suggestion` | str | Schema | Schema |

---

## Implementation Notes

1. **Single-file entrypoint** — all screens in `app.py` as `_<screen>_screen()` functions dispatched by `st.session_state["step"]`.
2. **Per-stage progress** — each of the four pipeline stages has its own `st.progress` bar updated via a `progress_callback` passed to `extract_structured_batch_with_validation`.
3. **Never re-upload on rerun** — file bytes stored in session state on first upload; `st.file_uploader` is only used to detect new additions.
4. **Back navigation is non-destructive** — navigating Back to Schema does not clear `rows`, `uploaded_files`, or `insights`.
5. **Streamlit version target** — ≥ 1.43. `@st.dialog` requires ≥ 1.36; `st.dataframe` single-row selection requires ≥ 1.35.
6. **Dialog close pattern** — the Entry Detail dialog uses `@st.dialog(width="large")` with no manual CSS width overrides. Close is handled by setting `show_entry_detail = False` and calling `st.rerun()`.
7. **`results_filter` state** — bound as the `key` of the filter `st.text_input`; Streamlit persists it automatically across reruns.