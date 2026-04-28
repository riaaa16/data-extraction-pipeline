# Streamlit UI Specs — Sprint 5 (Redesign)

## Overview & Design Philosophy

The redesigned app uses a single-page, sidebar-driven layout rather than a sequence of full-page screens. The left sidebar holds persistent navigation and global config (Ollama settings). The main content area renders the active step. A sticky progress stepper at the top of the main area always shows where the user is and what is complete.

The primary design goals are:
- **Reduce cognitive load**: expose only what is needed for the current step.
- **Clear progress feedback**: every async operation has a labelled, per-task progress bar — not a single global bar.
- **Recoverability**: users can jump back to any completed step without losing state.
- **Minimal visual noise**: use `st.container` cards, subtle dividers, and muted secondary text rather than raw unstyled widgets stacked top-to-bottom.

Colour palette (implement via `st.markdown` injected CSS or a `config.toml` theme):
- Background: `#F8F9FA`
- Card/container surface: `#FFFFFF`
- Primary accent: `#4F6CF7` (indigo)
- Success: `#22C55E`
- Warning: `#F59E0B`
- Error: `#EF4444`
- Muted text: `#6B7280`

---

## Global Layout

```
┌──────────────────┬──────────────────────────────────────────────┐
│   SIDEBAR        │  MAIN CONTENT AREA                           │
│                  │                                              │
│  App logo/title  │  ── Step Stepper (sticky) ──────────────    │
│                  │   1 Upload  2 Schema  3 Process  4 Results   │
│  ── Navigation   │                                              │
│  1 Upload    ●   │  <active step content>                       │
│  2 Schema    ○   │                                              │
│  3 Process   ○   │                                              │
│  4 Results   ○   │                                              │
│                  │                                              │
│  ── Ollama ────  │                                              │
│  Model           │                                              │
│  Base URL        │                                              │
│  Timeout         │                                              │
│  Retries         │                                              │
└──────────────────┴──────────────────────────────────────────────┘
```

### Sidebar — always visible

**App header**
- Logo mark (small indigo square icon) + text "DE Pipeline" in 18px semibold.
- Subtitle: "Data Extraction Pipeline" in muted 12px.

**Navigation**
- Five clickable step labels: Upload, Schema, Process, Results, Entry Detail.
- Each shows a status icon:
  - Grey circle = not yet reached.
  - Indigo filled circle = active.
  - Green checkmark = completed.
- Clicking a completed step navigates to it without resetting state.
- Clicking a future step is disabled (greyed out, cursor: not-allowed).

**Ollama Configuration** (collapsed `st.expander` by default, expands on first visit)
- `st.text_input` — Model name (default: `llama3.2:3b`)
- `st.text_input` — Base URL (default: `http://localhost:11434`)
- `st.number_input` — Timeout in minutes (default: 3, min: 1, max: 30)
- `st.number_input` — Validation max retries (default: 2, min: 0, max: 10)
- `st.button("Test connection")` — runs a lightweight ping to the Ollama base URL and shows `st.success` / `st.error` inline below the button.

Moving Ollama config to the sidebar means it is accessible from every step without cluttering the Schema screen.

---

## Step Stepper Component

Render at the top of the main area on every screen. Implemented as a single `st.markdown` block with injected HTML/CSS or as a custom component.

```
  ●──────────○──────────○──────────○
Upload    Schema    Process    Results
```

- Completed steps: filled indigo circle + indigo connecting line.
- Active step: filled indigo circle with white dot inside + bold label.
- Future steps: empty grey circle + grey line + muted label.
- The stepper is read-only; navigation is done from the sidebar.

---

## Screen 1 — Upload

### Purpose
Collect one or more files (.txt, .pdf, .docx) to be processed.

### Layout

```
┌─────────────────────────────────────────────────┐
│  Upload Files                                   │
│  Add the documents you want to extract from.   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │                                         │   │
│  │   Drag & drop files here                │   │
│  │   or  [ Browse files ]                  │   │
│  │   .txt  .pdf  .docx  · max 200 MB each  │   │
│  │                                         │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  Uploaded files                                 │
│  ┌──────────────────────────────────────────┐  │
│  │ 📄 interview_batch_1.pdf       120 KB  ✕ │  │
│  │ 📄 responses_march.docx         84 KB  ✕ │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│                      [ Continue → Schema ]      │
└─────────────────────────────────────────────────┘
```

### Components

**File uploader**
- `st.file_uploader(accept_multiple_files=True, type=["txt","pdf","docx"])`
- Wrap in a styled `st.container` with a dashed border (inject CSS via `st.markdown`).
- Helper text below the drop zone: "Accepts .txt, .pdf, .docx — up to 200 MB per file."

**Uploaded file list**
- Render as a bordered card below the uploader, only visible when at least one file is uploaded.
- Each row: file-type emoji icon + filename (truncated at 40 chars with ellipsis if needed) + size in KB/MB + a remove button (✕).
- Remove button calls `st.session_state.uploaded_files.pop(index)` and reruns.
- Show a muted count line above the list: "2 files · 204 KB total."

**Continue button**
- `st.button("Continue → Schema", type="primary")`
- Disabled (`disabled=True`) when `len(st.session_state.uploaded_files) == 0`.
- Positioned right-aligned using `st.columns([6,2])`.

### Session State
- `st.session_state.uploaded_files`: list of dicts `{name, bytes, size_bytes, type}`.
- Files persist across all subsequent steps.

---

## Screen 2 — Schema

### Purpose
Define extraction fields, choose segmentation mode, and save/load schema presets.

### Layout

```
┌──────────────────────────────────────────────────────┐
│  Schema Builder                                      │
│  Define the fields you want to extract from each    │
│  entry.                                             │
│                                                      │
│  ── Fields ──────────────────────────────────────── │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ Field 1                              [Remove] │   │
│  │ Name [participant_name]  Type [string    ▾]  │   │
│  │ Description [Full name of the participant  ] │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ Field 2                              [Remove] │   │
│  │ Name [sentiment]         Type [enum      ▾]  │   │
│  │ Description [Overall sentiment of entry    ] │   │
│  │ Enum values  [positive] [neutral] [negative] │   │
│  │              [ + add value ]                 │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  [ + Add Field ]                                     │
│                                                      │
│  ── Saved Schemas ───────────────────────────────── │
│  Name [my_schema          ] [💾 Save]               │
│  Load [schema_01          ▾] [📂 Load]              │
│                                                      │
│  ── Entry Separation ───────────────────────────── │
│  Mode  ● Deterministic  ○ Regex  ○ LLM             │
│                                                      │
│  <mode-specific controls — see below>               │
│                                                      │
│  [ ← Back ]                    [ Run Processing → ] │
└──────────────────────────────────────────────────────┘
```

### Components

**Field cards**
- Each field is rendered inside `st.container` with a light grey border.
- Header row: bold "Field N" label on the left, `st.button("Remove", key=f"remove_{i}")` on the right.
- Body: two columns — left `st.text_input("Name")`, right `st.selectbox("Type", ["string","integer","float","boolean","enum"])`.
- Full-width `st.text_input("Description")` below.
- If `type == "enum"`: render an additional row showing current enum values as removable tags + an inline `st.text_input` + `st.button("Add")` to add new values.
- Enum tag style: small indigo pill with an ✕ button.

**Add Field button**
- `st.button("+ Add Field")` appends a blank field to `st.session_state.schema_fields`.
- Always visible below the field list.

**Saved Schemas panel** (inside `st.expander("Saved Schemas", expanded=False)`)
- Save row: `st.text_input("Schema name")` + `st.button("💾 Save")` — writes JSON to `.depipeline_logs/saved_schemas/<name>.json`.
- Load row: `st.selectbox` of discovered schema files + `st.button("📂 Load")` — populates `st.session_state.schema_fields`.
- Show `st.success("Saved.")` / `st.success("Loaded.")` inline for 2 seconds after action.

**Entry Separation panel** (inside `st.expander("Entry Separation", expanded=True)`)
- `st.radio("Mode", ["Deterministic", "Regex", "LLM"])` — horizontal layout.

  *Deterministic mode*: no additional controls. Show info box: "Entries will be split using built-in heuristics. No configuration needed."

  *Regex mode*:
  - `st.text_area("Boundary patterns", height=100)` — one regex per line, monospace font via CSS.
  - Presets selectbox: "Interview — speakers", "Interview — timestamps", "Interview — speakers + timestamps" + `st.button("Apply preset")`.
  - LLM Regex Helper sub-expander:
    - `st.text_input("Sample heading")` + `st.button("Suggest regex")`.
    - On click: calls Ollama with the sample heading, streams result into `st.code` block.
    - `st.button("Use this pattern")` appends the suggestion to the patterns text area.

  *LLM mode*:
  - `st.text_area("Dataset description (optional)", height=80, placeholder="e.g. Interview transcripts, one participant per entry…")`.
  - Info box: "The LLM will identify entry boundaries and return start/end line ranges. Errors will halt processing with an actionable message."

**Navigation buttons**
- Left: `st.button("← Back")` returns to Upload.
- Right: `st.button("Run Processing →", type="primary")` — disabled if `len(schema_fields) == 0`. On click, validates that all fields have a name, then navigates to Process.

### Validation
- On "Run Processing →": check each field has a non-empty name. If not, show `st.error("All fields must have a name.")` and do not navigate.
- Enum fields must have at least one value; show `st.warning` otherwise (warn, do not block).

### Session State
- `st.session_state.schema_fields`: list of dicts `{name, type, description, enum_values}`.
- `st.session_state.separation_mode`: `"deterministic"` | `"regex"` | `"llm"`.
- `st.session_state.regex_patterns`: list of strings.
- `st.session_state.dataset_description`: string.

---

## Screen 3 — Processing

### Purpose
Run the full pipeline and give the user fine-grained progress feedback for each stage.

### Layout

```
┌──────────────────────────────────────────────────────┐
│  Processing                                          │
│  Running your pipeline. This may take a few minutes.│
│                                                      │
│  ── Stage Progress ──────────────────────────────── │
│                                                      │
│  1  Text Extraction          ████████████  100%  ✓  │
│     3 files extracted · 0 warnings                  │
│                                                      │
│  2  Segmentation             ████████░░░░   67%  ⟳  │
│     Splitting file2.pdf…                            │
│                                                      │
│  3  LLM Extraction           ░░░░░░░░░░░░    0%  –  │
│                                                      │
│  4  Validation               ░░░░░░░░░░░░    0%  –  │
│                                                      │
│  ── Live Metrics ───────────────────────────────── │
│  Files processed  2 / 3                             │
│  Entries found    14                                │
│  Retried          1                                 │
│  Elapsed          0:43                              │
│                                                      │
│  ── Warnings ───────────────────────────────────── │
│  ⚠ file1.pdf: page 4 had no extractable text       │
│                                                      │
│  [ ← Back to Schema ]        [ Continue → Results ] │
└──────────────────────────────────────────────────────┘
```

### Components

**Stage progress bars**
Each of the four pipeline stages gets its own labelled row:

```
Stage name     [progress bar]     XX%     [status icon]
Sub-label (current file / step)
```

- Implement as: `st.empty()` placeholder per stage, updated via `placeholder.markdown(...)` during the run.
- Status icons:
  - `–` grey dash = not started.
  - `⟳` spinning indicator (use `st.spinner` context or animated Unicode) = in progress.
  - `✓` green checkmark = complete.
  - `✕` red cross = failed.
- Progress values come from callbacks/generators yielded by the backend processing functions.
- Each bar uses `st.progress(value)` inside its placeholder.

**Stage sub-labels**
- Text line below each bar in muted colour showing the current item being processed (e.g. "Extracting: interview_batch_1.pdf (2 of 3)").
- Updated each time a new file/entry starts.

**Warnings panel**
- Only shown if `len(warnings) > 0`.
- Each warning rendered as `st.warning(text)` inside a scrollable container (max-height 120px via CSS).
- Count badge above the panel: "3 warnings".

**Live Metrics panel**
- Four `st.metric` widgets in a `st.columns(4)` row.
- Updated in real time during the run.
- Metrics: Files Processed, Entries Found, Retried, Elapsed.

**Error handling**
- If any stage raises a fatal error (especially LLM segmentation): stop the run, render `st.error(actionable_message)` above the stage bars, and enable the Back button. The Continue button remains disabled.
- Non-fatal warnings are collected and shown in the Warnings panel without stopping the run.

**Navigation buttons**
- "← Back to Schema": always enabled, returns to Schema without clearing uploaded files or schema.
- "Continue → Results": disabled until processing completes successfully. On success, auto-scroll to this button (use `st.balloons()` optionally) and enable it.

### Session State
- `st.session_state.processing_complete`: bool.
- `st.session_state.results`: list of entry dicts.
- `st.session_state.warnings`: list of warning strings.
- `st.session_state.processing_metrics`: dict `{files_processed, total_files, entries_found, retried, elapsed_seconds}`.

---

## Screen 4 — Results

### Purpose
Review all extracted entries, export to CSV, and select an entry to inspect or edit.

### Layout

```
┌──────────────────────────────────────────────────────┐
│  Results                                             │
│                                                      │
│  ── Summary ─────────────────────────────────────── │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐│
│  │ Total    │  │First-pass│  │ Retried  │  │Failed││
│  │   120    │  │   110    │  │    10    │  │   0  ││
│  └──────────┘  └──────────┘  └──────────┘  └──────┘│
│                                                      │
│  ┌─ Warnings (2) ──────────────────────────┐        │
│  │ ⚠ file1.pdf p.4: no extractable text   │        │
│  │ ⚠ entry 007: low confidence (0.41)     │        │
│  └─────────────────────────────────────────┘        │
│                                                      │
│  ── Results Table ───────────────────────────────── │
│  [ 🔍 Filter...              ]  [ 📥 Export CSV ]   │
│                                                      │
│  ID  │ participant_name │ sentiment │ confidence     │
│  001 │ Alex             │ negative  │ 0.82       [→] │
│  002 │ Sam              │ neutral   │ 0.77       [→] │
│  003 │ Jordan           │ positive  │ 0.91       [→] │
│                                                      │
│  Showing 1–25 of 120    [ < Prev ]  [ Next > ]      │
│                                                      │
│  ── Open Entry ──────────────────────────────────── │
│  Select entry  [ 001 ▾ ]   [ Open Entry Detail → ]  │
│                                                      │
│  [ ← Back to Processing ]                           │
└──────────────────────────────────────────────────────┘
```

### Components

**Summary metrics**
- `st.columns(4)` row of `st.metric` cards: Total, First-Pass Valid, Retried, Failed.
- Failed count in red if `> 0`, otherwise default colour.

**Warnings panel**
- Collapsed `st.expander(f"Warnings ({len(warnings)})", expanded=False)`.
- Each warning as a `st.warning` inside. Only render if `len(warnings) > 0`.

**Filter bar**
- `st.text_input("🔍 Filter…", placeholder="Type to filter by any field")` above the table.
- Filters rows client-side (Python rerun) by checking if the query string appears in any column value (case-insensitive).

**Results table**
- Render using `st.dataframe` with `use_container_width=True`.
- Columns: id + all schema field names + confidence. Confidence column formatted to 2 decimal places.
- `st.dataframe` selection mode: `selection_mode="single-row"` (Streamlit ≥ 1.35). Selecting a row sets `st.session_state.selected_entry_id`.
- Each row also has an inline "→" open button (rendered via `st.data_editor` with a button column as fallback for older Streamlit versions).
- Pagination: show 25 rows per page. Previous/Next buttons update `st.session_state.results_page`.

**Selectbox fallback**
- `st.selectbox("Select entry", options=[e["id"] for e in results])` below the table.
- Always synced with table row selection — clicking a table row also updates the selectbox value.

**Export CSV button**
- `st.download_button("📥 Export CSV", data=csv_bytes, file_name="results.csv", mime="text/csv")`.
- CSV includes all schema fields + confidence + id.
- Any edits made in Entry Detail are reflected in the export.

**Open Entry Detail button**
- `st.button("Open Entry Detail →", type="primary")` — disabled if no entry selected.
- Navigates to Entry Detail with `st.session_state.selected_entry_id` set.

### Session State
- `st.session_state.selected_entry_id`: str or None.
- `st.session_state.results_page`: int (default 0).
- `st.session_state.results_filter`: str.

---

## Screen 5 — Entry Detail

### Purpose
Inspect the raw source text for a single entry and edit its structured fields.

### Layout

```
┌──────────────────────────────────────────────────────┐
│  Entry Detail — #001                                 │
│                                                      │
│  ── Raw Text ────────────────────────────────────── │
│  ┌──────────────────────────────────────────────┐   │
│  │ Participant: Alex                            │   │
│  │ Date: 2026-04-01                             │   │
│  │ Sentiment: I felt very frustrated today…     │   │
│  │ …                                            │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ── Extracted Fields ────────────────────────────── │
│                                                      │
│  participant_name                                    │
│  [ Alex                          ]                  │
│                                                      │
│  sentiment                                          │
│  [ negative ▾ ]                                     │
│                                                      │
│  mentions_confusion                                  │
│  [✓] Yes  (checkbox)                                │
│                                                      │
│  confidence   0.82  (read-only badge)               │
│                                                      │
│  [ ← Back to Results ]               [ 💾 Save ]    │
└──────────────────────────────────────────────────────┘
```

### Components

**Entry header**
- "Entry Detail — #001" as `st.subheader`.
- Muted secondary line: filename + page/line range if available (e.g. "Source: interview_batch_1.pdf · lines 14–38").

**Raw text panel**
- `st.text_area("Raw Text", value=entry["raw_text"], height=200, disabled=True)`.
- Monospace font injected via CSS.
- Wrap in a bordered `st.container`.

**Field editors** (type-aware)
- `string` → `st.text_input`
- `integer` → `st.number_input(step=1)`
- `float` → `st.number_input(step=0.01)`
- `boolean` → `st.checkbox`
- `enum` → `st.selectbox` with enum values as options
- Each field rendered with its schema description as `help=` tooltip.
- Confidence displayed as a read-only `st.metric("Confidence", value=f"{conf:.2f}")` — not editable.

**Save button**
- `st.button("💾 Save", type="primary")`.
- On click: updates the matching entry in `st.session_state.results` and shows `st.success("Saved.")` for 2 seconds.
- Edits are immediately reflected in the Results table and CSV export.

**Navigation**
- `st.button("← Back to Results")` — left-aligned. Returns to Results with the same selected entry highlighted.
- Entry navigation: small `st.columns` with "‹ Previous entry" and "Next entry ›" links at the top right of the panel, allowing the user to step through entries without returning to the Results table each time.

### Session State
- Edits written back to `st.session_state.results[index]` on Save.

---

## CSS Injection Reference

Apply global styles once at app startup via `st.markdown("<style>...</style>", unsafe_allow_html=True)`:

```css
/* Card containers */
[data-testid="stVerticalBlock"] > div.card {
    background: #ffffff;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 16px;
}

/* Monospace text areas (raw text, regex) */
textarea.monospace { font-family: "JetBrains Mono", monospace; font-size: 13px; }

/* Enum tag pills */
.enum-tag {
    display: inline-flex; align-items: center; gap: 4px;
    background: #EEF2FF; color: #4F6CF7;
    border-radius: 999px; padding: 2px 10px; font-size: 12px;
}

/* Muted helper text */
.muted { color: #6B7280; font-size: 12px; }

/* Progress stage row */
.stage-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.stage-label { width: 160px; font-weight: 500; }
.stage-icon  { width: 24px; text-align: center; }
```

---

## Session State Master Reference

| Key | Type | Set by | Used by |
|-----|------|--------|---------|
| `uploaded_files` | list[dict] | Upload | All screens |
| `schema_fields` | list[dict] | Schema | Process, Results |
| `separation_mode` | str | Schema | Process |
| `regex_patterns` | list[str] | Schema | Process |
| `dataset_description` | str | Schema | Process |
| `ollama_model` | str | Sidebar | Process, Schema |
| `ollama_base_url` | str | Sidebar | Process, Schema |
| `ollama_timeout` | int | Sidebar | Process, Schema |
| `ollama_retries` | int | Sidebar | Process, Schema |
| `processing_complete` | bool | Process | Results |
| `results` | list[dict] | Process | Results, Entry Detail |
| `warnings` | list[str] | Process | Process, Results |
| `processing_metrics` | dict | Process | Process |
| `selected_entry_id` | str | Results | Entry Detail |
| `results_page` | int | Results | Results |
| `results_filter` | str | Results | Results |
| `current_step` | str | Navigation | Sidebar, Stepper |

---

## Implementation Notes for the Coding Agent

1. **Single-file entrypoint** — all screens live in `app.py`. Use a `render_<screen>()` function per screen, called based on `st.session_state.current_step`.
2. **Progress bars are per-stage, not global** — the backend processing function must yield progress events as a generator or via a callback. Each stage calls `stage_placeholder.progress(value)` independently.
3. **Never re-upload on rerun** — store file bytes in session state on first upload; do not re-read from `st.file_uploader` on every rerun.
4. **Disable future nav items** — use `st.sidebar.button(..., disabled=True)` for steps the user has not reached. Apply muted CSS to their labels.
5. **Back navigation is non-destructive** — going Back to Schema must not clear `st.session_state.results` or `uploaded_files`.
6. **Streamlit version target** — ≥ 1.35 for `st.dataframe` single-row selection. Add a `st.data_editor` fallback with a button column for older versions.
7. **Ollama connection test** — use `httpx.get(base_url, timeout=3)` in a `try/except` block; show result inline in sidebar without navigating.
8. **Elapsed timer** — implement with `time.time()` stored in session state at process start; update via `st.empty()` placeholder on each yield from the processing generator.