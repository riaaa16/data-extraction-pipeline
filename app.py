from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus, unquote_plus
from uuid import uuid4

import streamlit as st

from depipeline.errors import DepipelineError
from depipeline.extraction import extract_text_with_diagnostics
from depipeline.ollama_client import OllamaClient, OllamaConfig
from depipeline.schema import SchemaField, parse_schema_fields
from depipeline.segmentation import (
    segment_entries,
    segment_entries_llm_boundaries,
    segment_entries_regex,
)
from depipeline.structured_extraction import extract_structured_batch_with_validation

SUPPORTED_UPLOAD_TYPES = ["txt", "pdf", "docx"]
STEP_UPLOAD = "upload"
STEP_SCHEMA = "schema"
STEP_PROCESSING = "processing"
STEP_RESULTS = "results"
STEP_DETAIL = "detail"
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


def _init_state() -> None:
    defaults = {
        "step": STEP_UPLOAD,
        "session_id": uuid4().hex,
        "uploaded_files": [],
        "schema_fields": [
            {
                "name": "participant_name",
                "type": "string",
                "enum": "",
                "description": "",
            }
        ],
        "entries": [],
        "rows": [],
        "run_report": None,
        "pipeline_error": "",
        "processing_done": False,
        "selected_row_id": "",
        "processing_metrics": {
            "files": 0,
            "entries": 0,
            "processed": 0,
        },
        "processing_warnings": [],
        "ollama_model": DEFAULT_OLLAMA_MODEL,
        "ollama_base_url": DEFAULT_OLLAMA_BASE_URL,
        "ollama_timeout_minutes": 3,
        "segmentation_mode": "Deterministic",
        "dataset_description": "",
        "segmentation_regex_patterns": "",
        "segmentation_regex_pending": "",
        "validation_max_retries": 2,
        "sample_preview_count": 20,
        "schema_save_name": "",
        "saved_schema_name": "",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _progress_header() -> None:
    step = st.session_state["step"]
    ordered = [STEP_UPLOAD, STEP_SCHEMA, STEP_PROCESSING, STEP_RESULTS, STEP_DETAIL]
    labels = {
        STEP_UPLOAD: "Upload",
        STEP_SCHEMA: "Schema",
        STEP_PROCESSING: "Processing",
        STEP_RESULTS: "Results",
        STEP_DETAIL: "Entry Detail",
    }

    active_idx = ordered.index(step)
    chips = []
    for idx, key in enumerate(ordered):
        marker = "[x]" if idx <= active_idx else "[ ]"
        chips.append(f"{marker} {labels[key]}")

    st.caption(" -> ".join(chips))


def _set_step(step: str) -> None:
    st.session_state["step"] = step


def _saved_schema_dir() -> Path:
    path = Path(".depipeline_logs") / "saved_schemas"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _suggest_regex_from_sample(
    sample_heading: str,
    client: OllamaClient,
    dataset_description: str | None,
) -> str:
    cleaned = sample_heading.strip()
    if not cleaned:
        raise DepipelineError("Provide a sample heading to generate a regex")

    dataset_hint = str(dataset_description or "").strip()
    dataset_clause = (
        f"\nDataset description (optional):\n{dataset_hint}\n" if dataset_hint else ""
    )

    system_prompt = (
        "You generate a single Python regex that matches the START of entries. "
        "Return ONLY valid JSON. Do not include markdown.\n\n"
        "Rules:\n"
        "- Output schema: {\"regex\": \"<pattern>\"}\n"
        "- The regex should match the start of a line and include ^ anchor when appropriate.\n"
        "- Do not include delimiters like /.../.\n"
        "- Keep it as specific as possible to the sample heading.\n"
        + dataset_clause
    )
    user_prompt = (
        "Create a regex that matches headings like this sample. "
        "Return only JSON with the regex string.\n\n"
        f"Sample heading:\n{cleaned}"
    )

    result = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    try:
        payload = json.loads(result.content)
    except Exception as exc:
        raise DepipelineError("Regex suggestion did not return valid JSON") from exc

    regex = payload.get("regex") if isinstance(payload, dict) else None
    if not isinstance(regex, str) or not regex.strip():
        raise DepipelineError("Regex suggestion JSON must include a non-empty 'regex' string")

    try:
        re.compile(regex, re.MULTILINE)
    except re.error as exc:
        raise DepipelineError(f"Suggested regex is invalid: {exc}") from exc

    return regex


def _schema_payload_from_form(raw_fields: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for field in raw_fields:
        item: Dict[str, Any] = {
            "name": field.get("name", "").strip(),
            "type": field.get("type", "string").strip().lower(),
        }

        desc = field.get("description", "").strip()
        if desc:
            item["description"] = desc

        if item["type"] == "enum":
            item["enum"] = [
                part.strip()
                for part in field.get("enum", "").split(",")
                if part.strip()
            ]

        payload.append(item)

    return payload


def _build_schema_fields(raw_fields: List[Dict[str, str]]) -> List[SchemaField]:
    return parse_schema_fields(_schema_payload_from_form(raw_fields))


def _schema_fields_to_form(schema_fields: List[SchemaField]) -> List[Dict[str, str]]:
    form_fields: List[Dict[str, str]] = []
    for field in schema_fields:
        form_fields.append(
            {
                "name": field.name,
                "type": field.type,
                "enum": ", ".join(field.enum or []) if field.type == "enum" else "",
                "description": field.description or "",
            }
        )
    return form_fields


def _sanitize_schema_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return cleaned.strip("._-")


def _upload_screen() -> None:
    st.subheader("1) Upload Files")
    uploads = st.file_uploader(
        "Upload one or more files",
        type=SUPPORTED_UPLOAD_TYPES,
        accept_multiple_files=True,
    )

    normalized: List[Dict[str, Any]] = []
    for uploaded in uploads or []:
        normalized.append(
            {
                "name": uploaded.name,
                "bytes": uploaded.getvalue(),
                "size": uploaded.size,
            }
        )

    st.session_state["uploaded_files"] = normalized

    if normalized:
        st.write("Uploaded files")
        st.table(
            [
                {
                    "name": item["name"],
                    "size_bytes": item["size"],
                }
                for item in normalized
            ]
        )
    else:
        st.info("Upload at least one .txt, .docx, or .pdf file to continue.")

    if st.button("Continue -> Schema", disabled=not normalized):
        _set_step(STEP_SCHEMA)
        st.rerun()


def _schema_screen() -> None:
    st.subheader("2) Schema Builder")

    # Keep defaults visible even if prior session state accidentally persisted empty strings.
    if not st.session_state.get("ollama_model"):
        st.session_state["ollama_model"] = DEFAULT_OLLAMA_MODEL
    if not st.session_state.get("ollama_base_url"):
        st.session_state["ollama_base_url"] = DEFAULT_OLLAMA_BASE_URL
    if not st.session_state.get("ollama_timeout_minutes"):
        st.session_state["ollama_timeout_minutes"] = 3

    pending_regex = str(st.session_state.get("segmentation_regex_pending", "")).strip()
    if pending_regex:
        st.session_state["segmentation_regex_patterns"] = pending_regex
        st.session_state["segmentation_regex_pending"] = ""

    fields: List[Dict[str, str]] = st.session_state["schema_fields"]

    for idx, field in enumerate(fields):
        with st.container(border=True):
            cols = st.columns([3, 2, 4, 1])
            field["name"] = cols[0].text_input("Name", value=field.get("name", ""), key=f"name_{idx}")

            field_type = cols[1].selectbox(
                "Type",
                options=["string", "number", "boolean", "enum"],
                index=["string", "number", "boolean", "enum"].index(field.get("type", "string")),
                key=f"type_{idx}",
            )
            field["type"] = field_type

            field["description"] = cols[2].text_input(
                "Description",
                value=field.get("description", ""),
                key=f"description_{idx}",
            )

            if field_type == "enum":
                field["enum"] = st.text_input(
                    "Enum values (comma-separated)",
                    value=field.get("enum", ""),
                    key=f"enum_{idx}",
                )
            else:
                field["enum"] = ""

            if cols[3].button("Remove", key=f"remove_{idx}"):
                st.session_state["schema_fields"] = [
                    f for j, f in enumerate(fields) if j != idx
                ]
                st.rerun()

    saved_dir = _saved_schema_dir()
    saved_paths = sorted(saved_dir.glob("*.json"))
    saved_names = [path.stem for path in saved_paths]

    st.markdown("#### Saved Schemas")
    schema_tools = st.columns([2, 1, 2, 1])
    schema_tools[0].text_input("Schema name", key="schema_save_name")

    if schema_tools[1].button("Save Schema"):
        try:
            # validate before writing
            _build_schema_fields(fields)
            schema_name = _sanitize_schema_name(st.session_state.get("schema_save_name", ""))
            if not schema_name:
                raise ValueError("Enter a schema name before saving")

            payload = {"fields": _schema_payload_from_form(fields)}
            out_path = saved_dir / f"{schema_name}.json"
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            st.success(f"Saved schema: {out_path.name}")
            st.rerun()
        except (DepipelineError, ValueError) as exc:
            st.error(str(exc))

    schema_tools[2].selectbox(
        "Load schema",
        options=[""] + saved_names,
        key="saved_schema_name",
        help="Select a previously saved schema",
    )
    if schema_tools[3].button("Load"):
        selected = st.session_state.get("saved_schema_name", "")
        if not selected:
            st.warning("Select a saved schema to load")
        else:
            try:
                raw = json.loads((saved_dir / f"{selected}.json").read_text(encoding="utf-8"))
                loaded = parse_schema_fields(raw.get("fields", []) if isinstance(raw, dict) else raw)
                st.session_state["schema_fields"] = _schema_fields_to_form(loaded)
                st.success(f"Loaded schema: {selected}")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed loading schema '{selected}': {exc}")

    controls = st.columns([1, 1, 2])
    if controls[0].button("+ Add Field"):
        fields.append({"name": "", "type": "string", "enum": "", "description": ""})
        st.session_state["schema_fields"] = fields
        st.rerun()

    if controls[1].button("<- Back"):
        _set_step(STEP_UPLOAD)
        st.rerun()

    with controls[2]:
        st.selectbox(
            "Entry separation",
            options=["Deterministic", "Regex", "LLM (boundaries)"],
            key="segmentation_mode",
            help=(
                "Deterministic uses formatting rules (blank lines, bullets, anchors). "
                "Regex splits when your patterns match. "
                "LLM (boundaries) asks Ollama only for entry boundaries."
            ),
        )

        mode = str(st.session_state.get("segmentation_mode"))
        if mode == "Regex":
            st.text_area(
                "Entry boundary regex patterns (one per line)",
                key="segmentation_regex_patterns",
                height=120,
                help=(
                    "Each regex marks the START of a new entry. Uses Python regex with multiline mode."
                ),
            )

            st.markdown("**Regex helper (optional)**")
            sample_heading = st.text_input(
                "Sample heading",
                help="Paste one example heading line; we'll suggest a regex for it.",
            )
            if st.button("Suggest regex with LLM"):
                try:
                    timeout_minutes = float(st.session_state.get("ollama_timeout_minutes", 3))
                    timeout_seconds = max(10, int(timeout_minutes * 60))
                    helper_client = OllamaClient(
                        OllamaConfig(
                            model=st.session_state["ollama_model"],
                            base_url=st.session_state["ollama_base_url"],
                            timeout_seconds=timeout_seconds,
                        )
                    )
                    suggested = _suggest_regex_from_sample(
                        sample_heading,
                        helper_client,
                        dataset_description=str(st.session_state.get("dataset_description", "")).strip() or None,
                    )
                    st.session_state["segmentation_regex_pending"] = suggested
                    st.success("Regex suggested and applied")
                    st.rerun()
                except DepipelineError as exc:
                    st.error(str(exc))

            presets = {
                "Interview transcript - speakers": r"^[A-Z][A-Za-z .'-]{1,40}:\s+",
                "Interview transcript - timestamps": r"^\[\d{1,2}:\d{2}(?::\d{2})?\]\s+",
                "Interview transcript - speakers + timestamps": (
                    r"^[A-Z][A-Za-z .'-]{1,40}\s+\(\d{1,2}:\d{2}(?::\d{2})?\):\s+"
                ),
            }

            preset_name = st.selectbox(
                "Interview transcript presets",
                options=[""] + list(presets.keys()),
                help="Select a preset and click Apply to populate the regex patterns box.",
            )
            if preset_name and st.button("Apply preset"):
                st.session_state["segmentation_regex_patterns"] = presets[preset_name]
                st.rerun()

        if mode == "LLM (boundaries)":
            st.text_area(
                "Dataset description (optional)",
                key="dataset_description",
                height=100,
                help=(
                    "Describe what a single entry looks like (e.g., 'each bullet is a record', "
                    "'each chat turn is an entry', 'each ticket begins with Ticket ID'). "
                    "Used only for LLM entry separation."
                ),
            )

        st.text_input("Ollama model", key="ollama_model")
        st.text_input("Ollama base URL", key="ollama_base_url")
        st.number_input(
            "Ollama timeout (minutes)",
            min_value=1,
            max_value=30,
            key="ollama_timeout_minutes",
            help="Applies to entry separation (LLM mode) and structured extraction calls.",
        )
        st.number_input(
            "Validation max retries",
            min_value=0,
            max_value=5,
            key="validation_max_retries",
        )

    if st.button("Run Processing"):
        if not st.session_state.get("uploaded_files"):
            st.error("No uploaded files found. Please return to Upload and add files.")
            return

        try:
            parsed_fields = _build_schema_fields(fields)
        except DepipelineError as exc:
            st.error(str(exc))
            return

        st.session_state["schema_field_objects"] = parsed_fields
        st.session_state["processing_done"] = False
        st.session_state["pipeline_error"] = ""
        _set_step(STEP_PROCESSING)
        st.rerun()


def _persist_uploads() -> List[Path]:
    root = Path(".depipeline_logs") / "ui_uploads" / st.session_state["session_id"]
    root.mkdir(parents=True, exist_ok=True)

    stored_paths: List[Path] = []
    for index, file_obj in enumerate(st.session_state["uploaded_files"], start=1):
        name = Path(file_obj["name"]).name
        out_path = root / f"{index:03d}_{name}"
        out_path.write_bytes(file_obj["bytes"])
        stored_paths.append(out_path)

    return stored_paths


def _processing_screen() -> None:
    st.subheader("3) Processing")
    st.write("Running extraction -> segmentation -> LLM extraction -> validation")

    if st.session_state.get("processing_done"):
        if st.session_state.get("pipeline_error"):
            st.error(st.session_state["pipeline_error"])
        else:
            st.success("Processing complete.")
            report = st.session_state.get("run_report") or {}
            st.write(
                f"Entries: {report.get('total_entries', 0)} | "
                f"First-pass valid: {report.get('valid_first_pass', 0)} | "
                f"Retried: {report.get('retried', 0)} | "
                f"Failed: {report.get('failed', 0)}"
            )

        cols = st.columns(2)
        if cols[0].button("<- Back to Schema"):
            _set_step(STEP_SCHEMA)
            st.rerun()

        if cols[1].button("Continue -> Results", disabled=bool(st.session_state.get("pipeline_error"))):
            _set_step(STEP_RESULTS)
            st.rerun()
        return

    progress = st.progress(0)
    status = st.empty()
    metrics = st.empty()

    try:
        schema_fields: List[SchemaField] = st.session_state.get("schema_field_objects") or _build_schema_fields(
            st.session_state["schema_fields"]
        )

        timeout_minutes = float(st.session_state.get("ollama_timeout_minutes", 3))
        timeout_seconds = max(10, int(timeout_minutes * 60))
        client = OllamaClient(
            OllamaConfig(
                model=st.session_state["ollama_model"],
                base_url=st.session_state["ollama_base_url"],
                timeout_seconds=timeout_seconds,
            )
        )

        upload_paths = _persist_uploads()
        all_entries: List[Dict[str, Any]] = []
        warnings: List[str] = []

        total_files = max(1, len(upload_paths))
        for idx, path in enumerate(upload_paths, start=1):
            status.write(f"Extraction: {path.name} ({idx}/{total_files})")
            diagnostics = extract_text_with_diagnostics(path)
            for warning in diagnostics.warnings:
                warnings.append(f"{path.name}: {warning}")

            mode = str(st.session_state.get("segmentation_mode", "Deterministic"))
            if mode == "LLM (boundaries)":
                try:
                    entries = segment_entries_llm_boundaries(
                        diagnostics.text,
                        client,
                        dataset_description=str(st.session_state.get("dataset_description", "")).strip() or None,
                    )
                except DepipelineError as exc:
                    raise DepipelineError(
                        f"{path.name}: LLM entry separation failed ({exc}). "
                        "Increase the Ollama timeout, or switch Entry separation to Regex/Deterministic and retry."
                    ) from exc
            elif mode == "Regex":
                patterns = [
                    line
                    for line in str(st.session_state.get("segmentation_regex_patterns", "")).splitlines()
                    if line.strip()
                ]
                entries = segment_entries_regex(diagnostics.text, patterns)
            else:
                entries = segment_entries(diagnostics.text)

            for entry in entries:
                entry["id"] = f"{path.stem}-{path.suffix.lstrip('.')}-{entry['id']}"
            all_entries.extend(entries)

            progress.progress(int((idx / total_files) * 30))
            metrics.write(
                f"Files: {idx}/{total_files} | Entries so far: {len(all_entries)}"
            )

        status.write("LLM extraction + validation")
        progress.progress(45)

        rows, report = extract_structured_batch_with_validation(
            all_entries,
            schema_fields,
            client,
            raw_response_dir=".depipeline_logs/raw_responses",
            show_progress=False,
            max_retries=int(st.session_state["validation_max_retries"]),
        )

        progress.progress(100)
        status.write("Validation complete")
        metrics.write(
            f"Files: {total_files}/{total_files} | Entries: {len(all_entries)} | Processed: {len(rows)}"
        )

        st.session_state["entries"] = all_entries
        st.session_state["rows"] = rows
        st.session_state["run_report"] = report
        st.session_state["processing_warnings"] = warnings
        st.session_state["pipeline_error"] = ""
        st.session_state["processing_metrics"] = {
            "files": total_files,
            "entries": len(all_entries),
            "processed": len(rows),
        }
    except DepipelineError as exc:
        st.session_state["pipeline_error"] = str(exc)
    finally:
        st.session_state["processing_done"] = True
        st.rerun()


def _results_screen() -> None:
    st.subheader("4) Results")

    rows: List[Dict[str, Any]] = st.session_state.get("rows", [])
    schema_fields: List[SchemaField] = st.session_state.get("schema_field_objects", [])

    if not rows:
        st.warning("No processed rows found. Run processing first.")
        if st.button("<- Back to Processing"):
            _set_step(STEP_PROCESSING)
            st.rerun()
        return

    warnings = st.session_state.get("processing_warnings", [])
    for warning in warnings:
        st.warning(warning)

    report = st.session_state.get("run_report") or {}
    st.write(
        f"Total: {report.get('total_entries', 0)} | "
        f"First pass: {report.get('valid_first_pass', 0)} | "
        f"Retried: {report.get('retried', 0)} | "
        f"Failed: {report.get('failed', 0)}"
    )

    preview_columns = ["id"] + [field.name for field in schema_fields] + ["confidence"]
    preview_rows: List[Dict[str, Any]] = []
    for row in rows[: int(st.session_state["sample_preview_count"])]:
        preview = {key: row.get(key) for key in preview_columns}
        preview_rows.append(preview)

    st.caption(
        "Tip: Use row selection + 'Open Entry Detail' to avoid opening a new session in a new tab."
    )

    table_selection_id = ""
    try:
        event = st.dataframe(
            preview_rows,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
        )
        if hasattr(event, "selection") and getattr(event.selection, "rows", None):
            selected_idx = event.selection.rows[0]
            if 0 <= selected_idx < len(preview_rows):
                table_selection_id = str(preview_rows[selected_idx].get("id", ""))
    except TypeError:
        st.dataframe(preview_rows, width="stretch")

    csv_bytes = _rows_to_csv_bytes(rows, schema_fields)
    st.download_button(
        "Export CSV",
        data=csv_bytes,
        file_name="depipeline_results.csv",
        mime="text/csv",
    )

    row_ids = [str(row.get("id", "")) for row in rows]
    selected_default = st.session_state.get("selected_row_id", "")
    selected_index = row_ids.index(selected_default) if selected_default in row_ids else 0
    selected = st.selectbox(
        "Select entry",
        options=row_ids,
        index=selected_index,
        key="selected_row_picker",
    )

    effective_selected = table_selection_id or selected

    controls = st.columns(2)
    if controls[0].button("<- Back to Processing"):
        _set_step(STEP_PROCESSING)
        st.rerun()

    if controls[1].button("Open Entry Detail"):
        st.session_state["selected_row_id"] = effective_selected
        st.query_params["step"] = "detail"
        st.query_params["entry_id"] = quote_plus(effective_selected)
        _set_step(STEP_DETAIL)
        st.rerun()


def _rows_to_csv_bytes(rows: List[Dict[str, Any]], schema_fields: List[SchemaField]) -> bytes:
    columns = ["id", "raw_text"] + [field.name for field in schema_fields] + ["confidence"]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()

    for row in rows:
        writer.writerow({col: row.get(col) for col in columns})

    return buffer.getvalue().encode("utf-8")


def _entry_detail_screen() -> None:
    st.subheader("5) Entry Detail")

    rows: List[Dict[str, Any]] = st.session_state.get("rows", [])
    schema_fields: List[SchemaField] = st.session_state.get("schema_field_objects", [])
    selected_id = st.session_state.get("selected_row_id", "")

    if not rows:
        st.warning("No results available.")
        if st.button("Back to Results"):
            _set_step(STEP_RESULTS)
            st.rerun()
        return

    row = next((item for item in rows if str(item.get("id", "")) == selected_id), rows[0])
    st.session_state["selected_row_id"] = str(row.get("id", ""))
    st.query_params["step"] = "detail"
    st.query_params["entry_id"] = quote_plus(str(row.get("id", "")))

    st.text_area("Raw Text", value=str(row.get("raw_text", "")), height=220, disabled=True)

    edited: Dict[str, Any] = {}
    for field in schema_fields:
        key = f"detail_{row.get('id')}_{field.name}"
        current_value = row.get(field.name)

        if field.type == "number":
            numeric_value = float(current_value) if isinstance(current_value, (int, float)) else 0.0
            edited[field.name] = st.number_input(field.name, value=numeric_value, key=key)
        elif field.type == "boolean":
            edited[field.name] = st.checkbox(field.name, value=bool(current_value), key=key)
        elif field.type == "enum" and field.enum:
            options = list(field.enum)
            current = str(current_value) if current_value in options else options[0]
            edited[field.name] = st.selectbox(field.name, options=options, index=options.index(current), key=key)
        else:
            edited[field.name] = st.text_input(field.name, value="" if current_value is None else str(current_value), key=key)

    controls = st.columns(2)
    if controls[0].button("Save"):
        for idx, existing in enumerate(rows):
            if str(existing.get("id", "")) == str(row.get("id", "")):
                for key, value in edited.items():
                    rows[idx][key] = value
                st.session_state["rows"] = rows
                st.success("Saved edits")
                break

    if controls[1].button("<- Back to Results"):
        if "step" in st.query_params:
            del st.query_params["step"]
        if "entry_id" in st.query_params:
            del st.query_params["entry_id"]
        _set_step(STEP_RESULTS)
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Data Extraction Pipeline", layout="wide")
    st.title("Data Extraction Pipeline")
    st.caption("Guided workflow: Upload -> Schema -> Processing -> Results -> Entry Detail")

    _init_state()

    # Allow row-level links from Results table to open Entry Detail.
    qp_step = st.query_params.get("step")
    qp_entry = st.query_params.get("entry_id")
    if qp_step == "detail" and qp_entry:
        st.session_state["selected_row_id"] = unquote_plus(str(qp_entry))
        st.session_state["step"] = STEP_DETAIL

    _progress_header()

    step = st.session_state["step"]
    if step == STEP_UPLOAD:
        _upload_screen()
    elif step == STEP_SCHEMA:
        _schema_screen()
    elif step == STEP_PROCESSING:
        _processing_screen()
    elif step == STEP_RESULTS:
        _results_screen()
    else:
        _entry_detail_screen()


if __name__ == "__main__":
    main()
