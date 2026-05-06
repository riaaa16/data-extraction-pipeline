from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping
from urllib.parse import quote_plus, unquote_plus
from uuid import uuid4

from urllib import error as urllib_error
from urllib import request as urllib_request

import streamlit as st
import altair as alt

from depipeline.errors import DepipelineError
from depipeline.extraction import extract_text_with_diagnostics
from depipeline.insights import compute_insights
from depipeline.ollama_client import OllamaClient, OllamaConfig
from depipeline.schema import SchemaField, parse_schema_fields
from depipeline.segmentation import (
    segment_entries,
    segment_entries_llm_boundaries,
    segment_entries_regex,
)
from depipeline.structured_extraction import extract_structured_batch_with_validation

SUPPORTED_UPLOAD_TYPES = ["txt", "md", "markdown", "pdf", "docx"]
STEP_UPLOAD = "upload"
STEP_SCHEMA = "schema"
STEP_PROCESSING = "processing"
STEP_RESULTS = "results"
STEP_INSIGHTS = "insights"
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
PRIMARY_ACCENT = "#4F6CF7"


def _init_state() -> None:
    defaults = {
        "step": STEP_UPLOAD,
        "session_id": uuid4().hex,
        "uploaded_files": [],
        "upload_total_bytes": 0,
        "schema_fields": [
            {
                "id": uuid4().hex,
                "name": "participant_name",
                "type": "string",
                "enum": "",
                "description": "",
            }
        ],
        "schema_editor_ns": 0,
        "schema_ready": False,
        "entries": [],
        "rows": [],
        "run_report": None,
        "pipeline_error": "",
        "processing_done": False,
        "processing_active": False,
        "selected_row_id": "",
        "show_entry_detail": False,
        "processing_metrics": {
            "files": 0,
            "entries": 0,
            "processed": 0,
        },
        "processing_warnings": [],
        "insights": None,
        "ollama_model": DEFAULT_OLLAMA_MODEL,
        "ollama_base_url": DEFAULT_OLLAMA_BASE_URL,
        "ollama_timeout_minutes": 3,
        "segmentation_mode": "LLM",
        "segmentation_mode_user_set": False,
        "dataset_description": "",
        "segmentation_regex_patterns": "",
        "segmentation_regex_pending": "",
        "validation_max_retries": 2,
        "sample_preview_count": 20,
        "schema_save_name": "",
        "saved_schema_name": "",
        "regex_suggestion": "",
        "results_filter": "",
        "schema_manage_action": "",
        "schema_rename_to": "",
        "saved_schema_name_pending": "",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Backwards-compat: older session state may have schema fields without stable IDs.
    try:
        st.session_state["schema_fields"] = _ensure_schema_field_ids(
            list(st.session_state.get("schema_fields") or [])
        )
    except Exception:
        # If schema fields are malformed, keep whatever is there; validation will catch it.
        pass


def _ensure_schema_field_ids(fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for field in fields:
        field_id = field.get("id")
        if not isinstance(field_id, str) or not field_id.strip():
            field["id"] = uuid4().hex
    return fields


def _schema_form_with_fresh_ids(form_fields: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for field in form_fields:
        item: Dict[str, Any] = dict(field)
        item["id"] = uuid4().hex
        out.append(item)
    return out


def _mark_segmentation_mode_set() -> None:
    st.session_state["segmentation_mode_user_set"] = True


@dataclass(frozen=True)
class _StepInfo:
    key: str
    label: str


def _step_order() -> List[_StepInfo]:
    return [
        _StepInfo(STEP_UPLOAD, "Upload"),
        _StepInfo(STEP_SCHEMA, "Fields"),
        _StepInfo(STEP_PROCESSING, "Run"),
        _StepInfo(STEP_RESULTS, "Results"),
        _StepInfo(STEP_INSIGHTS, "Insights"),
    ]


def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _completed_steps() -> set[str]:
    completed = set()
    if st.session_state.get("uploaded_files"):
        completed.add(STEP_UPLOAD)
    if st.session_state.get("schema_ready"):
        completed.add(STEP_SCHEMA)
    if st.session_state.get("processing_done"):
        completed.add(STEP_PROCESSING)
    if st.session_state.get("rows"):
        completed.add(STEP_RESULTS)
    if st.session_state.get("insights"):
        completed.add(STEP_INSIGHTS)
    return completed


def _render_stepper() -> None:
    steps = _step_order()
    active = st.session_state["step"]
    completed = _completed_steps()

    st.markdown(
        """
        <style>
        .stepper {display:flex; justify-content:space-between; gap:8px; margin:8px 0 6px 0;}
        .stepper-item {flex:1; text-align:center;}
        .stepper-dot {width:18px; height:18px; border-radius:50%; display:inline-block;}
        .stepper-dot.done {background:#22C55E;}
        .stepper-dot.active {background:#4F6CF7;}
        .stepper-dot.future {background:#CBD5E1;}
        .stepper-label {text-align:center; color:#6B7280; font-size:12px; margin-top:6px;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    items = []
    for info in steps:
        if info.key in completed:
            cls = "done"
        elif info.key == active:
            cls = "active"
        else:
            cls = "future"

        dot = f"<span class='stepper-dot {cls}'></span>"
        label = f"<div class='stepper-label'>{info.label}</div>"
        items.append(f"<div class='stepper-item'>{dot}{label}</div>")

    st.markdown(f"<div class='stepper'>{''.join(items)}</div>", unsafe_allow_html=True)


def _test_ollama_connection(base_url: str, timeout_seconds: int) -> tuple[bool, str]:
    endpoint = f"{base_url.rstrip('/')}/api/tags"
    req = urllib_request.Request(endpoint, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
            if response.status != 200:
                return False, f"Unexpected status: {response.status}"
    except urllib_error.URLError as exc:
        return False, f"Unable to reach Ollama: {exc}"
    except Exception as exc:
        return False, f"Connection failed: {exc}"
    return True, "Ollama is reachable"


def _render_sidebar() -> None:
    steps = _step_order()
    active = st.session_state["step"]
    completed = _completed_steps()

    with st.sidebar:
        st.markdown(
            f"<div style='display:flex; align-items:center; gap:8px;'>"
            f"<div style='width:12px; height:12px; background:{PRIMARY_ACCENT}; border-radius:2px;'></div>"
            "<div style='font-weight:600;'>DE Pipeline</div>"
            "</div>"
            "<div style='color:#6B7280; font-size:12px; margin-top:4px;'>"
            "Data Extraction Pipeline</div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("**Navigation**")

        for info in steps:
            label = info.label
            is_active = info.key == active
            is_completed = info.key in completed
            icon = "✅" if is_completed else ("●" if is_active else "○")

            if info.key == STEP_UPLOAD:
                allowed = True
            elif info.key == STEP_SCHEMA:
                allowed = bool(st.session_state.get("uploaded_files"))
            elif info.key == STEP_PROCESSING:
                allowed = bool(st.session_state.get("schema_ready"))
            elif info.key == STEP_RESULTS:
                allowed = bool(st.session_state.get("processing_done"))
            else:
                allowed = bool(st.session_state.get("rows"))
            if info.key == STEP_INSIGHTS:
                allowed = bool(st.session_state.get("rows"))

            if st.button(f"{icon} {label}", disabled=not allowed, key=f"nav_{info.key}"):
                _set_step(info.key)
                st.rerun()

        st.markdown("---")
        settings_disabled = bool(
            st.session_state.get("processing_active")
            or (
                st.session_state.get("step") == STEP_PROCESSING
                and not st.session_state.get("processing_done")
            )
        )
        with st.expander("Model Settings", expanded=False):
            st.caption("Defaults work for most users.")
            st.text_input("Model", key="ollama_model", disabled=settings_disabled)
            st.text_input("Base URL", key="ollama_base_url", disabled=settings_disabled)
            st.number_input(
                "Timeout (minutes)",
                min_value=1,
                max_value=30,
                key="ollama_timeout_minutes",
                disabled=settings_disabled,
            )
            st.number_input(
                "Validation retries",
                min_value=0,
                max_value=10,
                key="validation_max_retries",
                disabled=settings_disabled,
            )
            if st.button("Test connection", disabled=settings_disabled):
                timeout_minutes = float(st.session_state.get("ollama_timeout_minutes", 3))
                timeout_seconds = max(5, int(timeout_minutes * 60))
                ok, message = _test_ollama_connection(
                    st.session_state.get("ollama_base_url", DEFAULT_OLLAMA_BASE_URL),
                    timeout_seconds,
                )
                if ok:
                    st.success(message)
                else:
                    st.error(message)


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

    # Strip control characters that can appear in model output (e.g., backspace).
    regex = re.sub(r"[\x00-\x1F\x7F]", "", regex).strip()
    regex = re.sub(r"\s+", " ", regex)

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
    st.subheader("Upload Files")
    st.caption("Add the documents you want to process.")

    uploads = st.file_uploader(
        "Drag & drop files here",
        type=SUPPORTED_UPLOAD_TYPES,
        accept_multiple_files=True,
    )

    if uploads:
        existing = {(f["name"], f["size"]) for f in st.session_state["uploaded_files"]}
        for uploaded in uploads:
            key = (uploaded.name, uploaded.size)
            if key not in existing:
                st.session_state["uploaded_files"].append(
                    {
                        "name": uploaded.name,
                        "bytes": uploaded.getvalue(),
                        "size": uploaded.size,
                    }
                )
                existing.add(key)

    total_bytes = sum(item["size"] for item in st.session_state["uploaded_files"])
    st.session_state["upload_total_bytes"] = total_bytes

    if st.session_state["uploaded_files"]:
        st.markdown("**Uploaded files**")
        st.caption(
            f"{len(st.session_state['uploaded_files'])} files · { _format_bytes(total_bytes) } total"
        )
        for idx, item in enumerate(list(st.session_state["uploaded_files"])):
            cols = st.columns([6, 2, 1], vertical_alignment="center")
            cols[0].write(f"📄 {item['name']}")
            cols[1].caption(_format_bytes(item["size"]))
            if cols[2].button("✕", key=f"remove_upload_{idx}", width="stretch"):
                st.session_state["uploaded_files"].pop(idx)
                st.rerun()
    else:
        st.info("Upload at least one .txt, .md, .docx, or .pdf file to continue.")

    _, btn_col = st.columns([6, 2])
    if btn_col.button(
        "Continue → Fields",
        disabled=not st.session_state["uploaded_files"],
        type="primary",
        width="stretch",
    ):
        _set_step(STEP_SCHEMA)
        st.rerun()


def _schema_screen() -> None:
    st.subheader("Output Fields")
    st.caption("Choose the columns you want to see in your results.")

    # Keep defaults visible even if prior session state accidentally persisted empty strings.
    if not st.session_state.get("ollama_model"):
        st.session_state["ollama_model"] = DEFAULT_OLLAMA_MODEL
    if not st.session_state.get("ollama_base_url"):
        st.session_state["ollama_base_url"] = DEFAULT_OLLAMA_BASE_URL
    if not st.session_state.get("ollama_timeout_minutes"):
        st.session_state["ollama_timeout_minutes"] = 3

    if st.session_state.get("segmentation_mode") not in {"Deterministic", "Regex", "LLM"}:
        st.session_state["segmentation_mode"] = "LLM"

    if not st.session_state.get("segmentation_mode_user_set"):
        st.session_state["segmentation_mode"] = "LLM"

    pending_regex = str(st.session_state.get("segmentation_regex_pending", "")).strip()
    if pending_regex:
        st.session_state["segmentation_regex_patterns"] = pending_regex
        st.session_state["segmentation_regex_pending"] = ""

    schema_ns = int(st.session_state.get("schema_editor_ns", 0))
    fields: List[Dict[str, Any]] = _ensure_schema_field_ids(
        list(st.session_state.get("schema_fields") or [])
    )
    remove_field_id: str | None = None

    for field in fields:
        field_id = str(field.get("id") or "")
        with st.container(border=True):
            cols = st.columns([3, 2, 4, 2], vertical_alignment="bottom")
            field["name"] = cols[0].text_input(
                "Name",
                value=field.get("name", ""),
                key=f"schema_{schema_ns}_name_{field_id}",
            )

            field_type = cols[1].selectbox(
                "Type",
                options=["string", "number", "boolean", "enum"],
                index=["string", "number", "boolean", "enum"].index(field.get("type", "string")),
                key=f"schema_{schema_ns}_type_{field_id}",
            )
            field["type"] = field_type

            field["description"] = cols[2].text_input(
                "Description",
                value=field.get("description", ""),
                key=f"schema_{schema_ns}_description_{field_id}",
            )

            if field_type == "enum":
                field["enum"] = st.text_input(
                    "Enum values (comma-separated)",
                    value=field.get("enum", ""),
                    key=f"schema_{schema_ns}_enum_{field_id}",
                )
            else:
                field["enum"] = ""

            if cols[3].button(
                "Remove",
                key=f"schema_{schema_ns}_remove_{field_id}",
                width="stretch",
            ):
                remove_field_id = field_id

    if remove_field_id:
        st.session_state["schema_fields"] = [
            f for f in fields if str(f.get("id") or "") != remove_field_id
        ]
        st.rerun()

    saved_dir = _saved_schema_dir()

    add_cols = st.columns([1, 5], vertical_alignment="bottom")
    if add_cols[0].button("+ Add Field"):
        fields.append(
            {
                "id": uuid4().hex,
                "name": "",
                "type": "string",
                "enum": "",
                "description": "",
            }
        )
        st.session_state["schema_fields"] = fields
        st.rerun()

    st.session_state["schema_fields"] = fields

    with st.expander("Saved Schemas", expanded=False):
        # ── Save current schema ───────────────────────────────────────────────
        st.caption("Save current schema as")
        save_cols = st.columns([4, 1], vertical_alignment="top")
        save_cols[0].text_input(
            "Save current schema as",
            key="schema_save_name",
            placeholder="e.g. interview-fields",
            label_visibility="collapsed",
        )
        if save_cols[1].button("💾 Save", width="stretch"):
            try:
                _build_schema_fields(fields)
                schema_name = _sanitize_schema_name(st.session_state.get("schema_save_name", ""))
                if not schema_name:
                    raise ValueError("Enter a schema name before saving")
                payload = {"fields": _schema_payload_from_form(fields)}
                out_path = saved_dir / f"{schema_name}.json"
                out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                st.session_state["schema_manage_action"] = ""
                st.success(f"Saved as '{schema_name}'.")
            except (DepipelineError, ValueError) as exc:
                st.error(str(exc))

        # ── Manage saved schemas ──────────────────────────────────────────────
        saved_paths = sorted(saved_dir.glob("*.json"))
        saved_names = [p.stem for p in saved_paths]

        if saved_names:
            st.markdown("---")

            # Apply any pending selection set by rename/delete handlers in the
            # previous run (must happen before the selectbox is instantiated).
            pending = st.session_state.get("saved_schema_name_pending", "")
            if pending and pending in saved_names:
                st.session_state["saved_schema_name"] = pending
            st.session_state["saved_schema_name_pending"] = ""

            # Ensure the stored selection is still valid after a rename/delete.
            if st.session_state.get("saved_schema_name", "") not in saved_names:
                st.session_state["saved_schema_name"] = saved_names[0]

            st.caption("Select a saved schema")
            mgmt_cols = st.columns([4, 1, 1, 1], vertical_alignment="top")
            mgmt_cols[0].selectbox(
                "Select a saved schema",
                options=saved_names,
                key="saved_schema_name",
                label_visibility="collapsed",
            )
            selected = st.session_state.get("saved_schema_name", "")

            if mgmt_cols[1].button("📂 Load", width="stretch"):
                try:
                    raw = json.loads((saved_dir / f"{selected}.json").read_text(encoding="utf-8"))
                    loaded = parse_schema_fields(raw.get("fields", []) if isinstance(raw, dict) else raw)
                    st.session_state["schema_fields"] = _schema_form_with_fresh_ids(
                        _schema_fields_to_form(loaded)
                    )
                    st.session_state["schema_editor_ns"] = int(
                        st.session_state.get("schema_editor_ns", 0)
                    ) + 1
                    st.session_state["schema_manage_action"] = ""
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed loading '{selected}': {exc}")

            action = st.session_state.get("schema_manage_action", "")

            if mgmt_cols[2].button(
                "✏️ Rename",
                width="stretch",
                type="primary" if action == "rename" else "secondary",
            ):
                if action == "rename":
                    st.session_state["schema_manage_action"] = ""
                else:
                    st.session_state["schema_manage_action"] = "rename"
                    st.session_state["schema_rename_to"] = selected
                st.rerun()

            if mgmt_cols[3].button(
                "🗑️ Delete",
                width="stretch",
                type="primary" if action == "delete" else "secondary",
            ):
                if action == "delete":
                    st.session_state["schema_manage_action"] = ""
                else:
                    st.session_state["schema_manage_action"] = "delete"
                st.rerun()

            # Inline rename form
            if action == "rename":
                st.caption("New name")
                rename_cols = st.columns([4, 1], vertical_alignment="top")
                rename_cols[0].text_input(
                    "New name",
                    key="schema_rename_to",
                    label_visibility="collapsed",
                )
                if rename_cols[1].button("✓ Confirm", width="stretch", type="primary"):
                    new_name = _sanitize_schema_name(st.session_state.get("schema_rename_to", ""))
                    if not new_name:
                        st.error("Enter a valid name.")
                    elif new_name == selected:
                        st.session_state["schema_manage_action"] = ""
                        st.rerun()
                    else:
                        new_path = saved_dir / f"{new_name}.json"
                        if new_path.exists():
                            st.error(f"A schema named '{new_name}' already exists.")
                        else:
                            (saved_dir / f"{selected}.json").rename(new_path)
                            st.session_state["saved_schema_name_pending"] = new_name
                            st.session_state["schema_manage_action"] = ""
                            st.rerun()

            # Inline delete confirmation
            elif action == "delete":
                st.warning(f"Delete **{selected}**? This cannot be undone.")
                confirm_cols = st.columns([1, 1, 4], vertical_alignment="top")
                if confirm_cols[0].button("Cancel"):
                    st.session_state["schema_manage_action"] = ""
                    st.rerun()
                if confirm_cols[1].button("🗑️ Delete", type="primary"):
                    (saved_dir / f"{selected}.json").unlink(missing_ok=True)
                    remaining = [p.stem for p in sorted(saved_dir.glob("*.json"))]
                    st.session_state["saved_schema_name_pending"] = remaining[0] if remaining else ""
                    st.session_state["schema_manage_action"] = ""
                    st.rerun()

    with st.expander("Advanced: Entry Separation", expanded=False):
        st.caption("Optional: adjust how entries are split. Defaults work for most files.")
        st.radio(
            "Mode",
            options=["Deterministic", "Regex", "LLM"],
            horizontal=True,
            key="segmentation_mode",
            on_change=_mark_segmentation_mode_set,
        )

        mode = str(st.session_state.get("segmentation_mode"))
        if mode == "Deterministic":
            st.info("Automatic splitting is enabled. No configuration needed.")
        elif mode == "Regex":
            st.text_area(
                "Boundary patterns (one per line)",
                key="segmentation_regex_patterns",
                height=100,
                help="Each pattern marks the start of a new entry.",
            )

            with st.expander("Pattern helper", expanded=False):
                sample_heading = st.text_input(
                    "Sample heading",
                    help="Paste one example heading line; we'll suggest a pattern.",
                )
                helper_actions = st.columns([1, 5], vertical_alignment="bottom")
                if helper_actions[0].button("Suggest regex"):
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
                        st.session_state["regex_suggestion"] = suggested
                    except DepipelineError as exc:
                        st.error(str(exc))

                if st.session_state.get("regex_suggestion"):
                    st.code(st.session_state["regex_suggestion"], language="text")
                    if st.button("Use this pattern"):
                        st.session_state["segmentation_regex_pending"] = st.session_state["regex_suggestion"]
                        st.rerun()
        else:
            st.text_area(
                "Dataset description (optional)",
                key="dataset_description",
                height=80,
                help=(
                    "Describe what a single entry looks like (e.g., 'each bullet is a record', "
                    "'each chat turn is an entry', 'each ticket begins with Ticket ID')."
                ),
            )
            st.info(
                "We'll infer entry boundaries from your description. "
                "If we cannot, processing will stop with a clear error message."
            )

    cols = st.columns([6, 2], vertical_alignment="bottom")
    if cols[0].button("← Back"):
        _set_step(STEP_UPLOAD)
        st.rerun()

    run_align = cols[1].columns([1, 1], vertical_alignment="bottom")
    if run_align[1].button("Start Processing →", type="primary"):
        if not st.session_state.get("uploaded_files"):
            st.error("No uploaded files found. Please return to Upload and add files.")
            return

        try:
            parsed_fields = _build_schema_fields(fields)
        except DepipelineError as exc:
            st.error(str(exc))
            return

        st.session_state["schema_field_objects"] = parsed_fields
        st.session_state["schema_ready"] = True
        st.session_state["processing_done"] = False
        st.session_state["processing_active"] = True
        st.session_state["pipeline_error"] = ""
        st.session_state["insights"] = None
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
    st.subheader("Processing Files")
    st.caption("Processing your files. You will see results when it's done.")

    if st.session_state.get("processing_done"):
        st.session_state["processing_active"] = False
        if st.session_state.get("pipeline_error"):
            st.error(st.session_state["pipeline_error"])

            msg = str(st.session_state.get("pipeline_error") or "")
            ollama_down = any(
                needle in msg.lower()
                for needle in [
                    "unable to reach ollama",
                    "unable to connect to ollama",
                    "timed out calling ollama",
                ]
            )
            if ollama_down:
                restart_cols = st.columns([6, 2], vertical_alignment="bottom")
                if restart_cols[0].button("Restart process"):
                    st.session_state["processing_done"] = False
                    st.session_state["pipeline_error"] = ""
                    st.session_state["rows"] = []
                    st.session_state["entries"] = []
                    st.session_state["run_report"] = {}
                    st.rerun()
        else:
            st.success("Ready. Your results are available.")
            report = st.session_state.get("run_report") or {}
            with st.expander("Run summary", expanded=False):
                metric_cols = st.columns(4)
                metric_cols[0].metric("Total entries", report.get("total_entries", 0))
                metric_cols[1].metric("First-pass valid", report.get("valid_first_pass", 0))
                metric_cols[2].metric("Retried", report.get("retried", 0))
                metric_cols[3].metric("Failed", report.get("failed", 0))

        cols = st.columns([6, 2], vertical_alignment="bottom")
        if cols[0].button("← Back to Fields"):
            _set_step(STEP_SCHEMA)
            st.rerun()

        if cols[1].button(
            "View Results →",
            disabled=bool(st.session_state.get("pipeline_error")),
            type="primary",
            width="stretch",
        ):
            _set_step(STEP_RESULTS)
            st.rerun()
        return

    st.session_state["processing_active"] = True
    overall_bar = st.progress(0)
    status = st.empty()
    status.write("Processing files...")

    with st.expander("Processing details", expanded=False):
        st.markdown("**1 — Read files**")
        extraction_bar = st.progress(0)
        st.markdown("**2 — Split entries**")
        segmentation_bar = st.progress(0)
        st.markdown("**3 — Extract fields**")
        llm_bar = st.progress(0)
        st.markdown("**4 — Final checks**")
        validation_bar = st.progress(0)
        metrics = st.empty()

    def _set_overall(pct: int) -> None:
        overall_bar.progress(min(100, max(0, int(pct))))

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
            diagnostics = extract_text_with_diagnostics(path)
            for warning in diagnostics.warnings:
                warnings.append(f"{path.name}: {warning}")

            extraction_bar.progress(int((idx / total_files) * 100))
            _set_overall(int((idx / total_files) * 20))

            mode = str(st.session_state.get("segmentation_mode", "Deterministic"))
            if mode in {"LLM", "LLM (boundaries)"}:
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

            segmentation_bar.progress(int((idx / total_files) * 100))
            _set_overall(20 + int((idx / total_files) * 20))

            for entry in entries:
                entry["id"] = f"{path.stem}-{path.suffix.lstrip('.')}-{entry['id']}"
            all_entries.extend(entries)

            metrics.write(
                f"Files: {idx}/{total_files} | Entries: {len(all_entries)}"
            )

        llm_bar.progress(0)
        _set_overall(40)
        status.write("Extracting fields...")

        def _on_llm_progress(
            progress_index: int,
            progress_total: int,
            entry: Mapping[str, object],
            attempt: int,
            max_retries: int,
        ) -> None:
            total = max(1, int(progress_total))
            base = max(0, int(progress_index) - 1)
            denom = max(1, int(max_retries) + 1)
            within = (int(attempt) + 1) / denom
            pct = int(((base + within) / total) * 100)
            llm_bar.progress(min(99, max(0, pct)))
            _set_overall(40 + int(((base + within) / total) * 50))

            metrics.write(
                f"Files: {total_files}/{total_files} | Entries: {len(all_entries)} | "
                f"Extracted: {progress_index}/{progress_total}"
            )

        rows, report = extract_structured_batch_with_validation(
            all_entries,
            schema_fields,
            client,
            raw_response_dir=".depipeline_logs/raw_responses",
            show_progress=False,
            max_retries=int(st.session_state["validation_max_retries"]),
            progress_callback=_on_llm_progress,
        )

        llm_bar.progress(100)
        validation_bar.progress(100)
        _set_overall(100)
        status.write("Finalizing results...")
        metrics.write(
            f"Files: {total_files}/{total_files} | Entries: {len(all_entries)} | Processed: {len(rows)}"
        )

        st.session_state["entries"] = all_entries
        st.session_state["rows"] = rows
        st.session_state["run_report"] = report
        st.session_state["processing_warnings"] = warnings
        st.session_state["pipeline_error"] = ""
        st.session_state["insights"] = compute_insights(rows, schema_fields)
        st.session_state["processing_metrics"] = {
            "files": total_files,
            "entries": len(all_entries),
            "processed": len(rows),
        }
    except DepipelineError as exc:
        st.session_state["pipeline_error"] = str(exc)
    finally:
        st.session_state["processing_active"] = False
        st.session_state["processing_done"] = True
        st.rerun()


def _insights_screen() -> None:
    st.subheader("Insights")
    st.caption("Aggregated themes and simple counts over your processed dataset.")

    rows: List[Dict[str, Any]] = st.session_state.get("rows", [])
    schema_fields: List[SchemaField] = st.session_state.get("schema_field_objects", [])

    if not rows:
        if st.session_state.get("pipeline_error"):
            st.error(str(st.session_state.get("pipeline_error")))
        else:
            st.warning("No processed rows found in this session.")
            st.caption(
                "If you can see Results in another tab, you may have opened a new browser session. "
                "Use the in-app navigation in the same tab, or re-run Processing."
            )
        controls = st.columns([6, 2], vertical_alignment="bottom")
        if controls[0].button("← Back to Processing"):
            _set_step(STEP_PROCESSING)
            st.rerun()
        return

    insights = st.session_state.get("insights")
    if insights is None:
        insights = compute_insights(rows, schema_fields)
        st.session_state["insights"] = insights

    non_empty_text = sum(
        1
        for row in rows
        if isinstance(row.get("raw_text"), str) and str(row.get("raw_text")).strip()
    )
    if not insights.keywords and not insights.themes and not insights.field_breakdowns:
        st.info(
            "Insights can’t be produced yet because there isn’t enough usable data. "
            "This usually happens when `raw_text` is empty for all rows and there are no low-cardinality fields to summarize."
        )
    elif non_empty_text == 0:
        st.info(
            "Themes/keywords are unavailable because none of the rows include non-empty `raw_text`. "
            "Field breakdowns (if any) are still shown below."
        )

    _count_axis = alt.Axis(tickMinStep=1, format="d")

    with st.container(border=True):
        st.markdown("**Themes**")
        if insights.themes:
            theme_data = [
                {"theme": item.theme, "count": int(item.count)} for item in insights.themes
            ]
            theme_chart = (
                alt.Chart(alt.Data(values=theme_data))
                .mark_bar()
                .encode(
                    x=alt.X("count:Q", title="Count", axis=_count_axis),
                    y=alt.Y("theme:N", sort="-x", title="Theme"),
                    color=alt.Color(
                        "theme:N",
                        scale=alt.Scale(scheme="tableau10"),
                        legend=None,
                    ),
                    tooltip=["theme:N", "count:Q"],
                )
            )
            st.altair_chart(theme_chart, width="stretch")
        else:
            st.caption("No themes available (no text found).")

    with st.container(border=True):
        st.markdown("**Keywords**")
        if insights.keywords:
            keyword_data = [
                {"keyword": item.keyword, "count": int(item.count)}
                for item in insights.keywords
            ]
            keyword_chart = (
                alt.Chart(alt.Data(values=keyword_data))
                .mark_bar()
                .encode(
                    x=alt.X("count:Q", title="Count", axis=_count_axis),
                    y=alt.Y("keyword:N", sort="-x", title="Keyword"),
                    color=alt.Color(
                        "keyword:N",
                        scale=alt.Scale(scheme="tableau10"),
                        legend=None,
                    ),
                    tooltip=["keyword:N", "count:Q"],
                )
            )
            st.altair_chart(keyword_chart, width="stretch")
        else:
            st.caption("No keywords available (no text found).")

    if insights.field_breakdowns:
        st.markdown("---")
        st.markdown("**Field breakdowns**")
        for field_name, breakdown in insights.field_breakdowns.items():
            with st.container(border=True):
                st.markdown(f"**{field_name}**")
                breakdown_data = [
                    {"value": str(value), "count": int(count)} for value, count in breakdown
                ]
                breakdown_chart = (
                    alt.Chart(alt.Data(values=breakdown_data))
                    .mark_bar()
                    .encode(
                        x=alt.X("count:Q", title="Count", axis=_count_axis),
                        y=alt.Y("value:N", sort="-x", title="Value"),
                        color=alt.Color(
                            "value:N",
                            scale=alt.Scale(scheme="tableau10"),
                            legend=None,
                        ),
                        tooltip=["value:N", "count:Q"],
                    )
                )
                st.altair_chart(breakdown_chart, width="stretch")

    controls = st.columns([6, 2], vertical_alignment="bottom")
    if controls[0].button("← Back to Results"):
        _set_step(STEP_RESULTS)
        st.rerun()


def _results_screen() -> None:
    rows: List[Dict[str, Any]] = st.session_state.get("rows", [])
    schema_fields: List[SchemaField] = st.session_state.get("schema_field_objects", [])

    if not rows:
        st.warning("No processed rows found. Run processing first.")
        if st.button("← Back to Processing"):
            _set_step(STEP_PROCESSING)
            st.rerun()
        return

    header_cols = st.columns([6, 2], vertical_alignment="bottom")
    with header_cols[0]:
        st.subheader("Results")
        st.caption("Review and export your results.")
    with header_cols[1]:
        st.markdown(
            """
            <style>
            div[data-testid="stDownloadButton"] > button {height: 72px;}
            </style>
            """,
            unsafe_allow_html=True,
        )
        csv_bytes = _rows_to_csv_bytes(rows, schema_fields)
        st.download_button(
            "📥 Export CSV",
            data=csv_bytes,
            file_name="depipeline_results.csv",
            mime="text/csv",
            width="stretch",
        )

    # Warnings — collapsed expander
    warnings = st.session_state.get("processing_warnings", [])
    if warnings:
        with st.expander(f"Warnings ({len(warnings)})", expanded=False):
            for warning in warnings:
                st.warning(warning)

    # Search bar
    preview_columns = ["id"] + [field.name for field in schema_fields] + ["confidence"]
    searchable_fields = ["id"] + [f.name for f in schema_fields] + ["raw_text", "confidence"]
    field_hint = ", ".join(searchable_fields[:6]) + (" …" if len(searchable_fields) > 6 else "")

    filter_text = st.text_input(
        "Search results",
        placeholder="🔍 Search by ID, field values, or raw text…",
        key="results_filter",
        help=f"Searches across all rows for matches in: {field_hint}",
        label_visibility="collapsed",
    )

    preview_rows: List[Dict[str, Any]] = []
    if filter_text.strip():
        q = filter_text.strip().lower()
        for row in rows:
            projected = {key: row.get(key) for key in preview_columns}
            # Also match against raw_text which is not in preview_columns
            all_values = list(projected.values()) + [row.get("raw_text", "")]
            if any(q in str(v).lower() for v in all_values):
                preview_rows.append(projected)
    else:
        for row in rows[: int(st.session_state["sample_preview_count"])]:
            preview_rows.append({key: row.get(key) for key in preview_columns})

    if filter_text.strip():
        match_word = "match" if len(preview_rows) == 1 else "matches"
        st.caption(
            f"**{len(preview_rows)} {match_word}** across all {len(rows)} rows."
        )
    else:
        st.caption(
            f"Showing {min(len(preview_rows), int(st.session_state['sample_preview_count']))} "
            f"of {len(rows)} rows."
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

    row_ids = [str(row.get("id", "")) for row in rows]
    selected_default = st.session_state.get("selected_row_id", "")
    selected_index = row_ids.index(selected_default) if selected_default in row_ids else 0
    entry_row = st.columns([6, 2], vertical_alignment="bottom")
    selected = entry_row[0].selectbox(
        "Select entry",
        options=row_ids,
        index=selected_index,
        key="selected_row_picker",
    )

    effective_selected = table_selection_id or selected

    if entry_row[1].button("View Entry Detail →", width="stretch"):
        st.session_state["selected_row_id"] = effective_selected
        st.session_state["show_entry_detail"] = True
        st.rerun()

    controls = st.columns([6, 2], vertical_alignment="bottom")
    if controls[0].button("← Back to Processing"):
        _set_step(STEP_PROCESSING)
        st.rerun()

    if controls[1].button("View Insights →", width="stretch"):
        st.session_state["selected_row_id"] = effective_selected
        _set_step(STEP_INSIGHTS)
        st.rerun()

    if st.session_state.get("show_entry_detail"):
        _render_entry_detail_dialog()


def _rows_to_csv_bytes(rows: List[Dict[str, Any]], schema_fields: List[SchemaField]) -> bytes:
    columns = ["id", "raw_text"] + [field.name for field in schema_fields] + ["confidence"]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()

    for row in rows:
        writer.writerow({col: row.get(col) for col in columns})

    return buffer.getvalue().encode("utf-8")


@st.dialog("Entry Detail", width="large")
def _render_entry_detail_dialog() -> None:
    _render_entry_detail_contents()
    st.divider()
    close_cols = st.columns([6, 2], vertical_alignment="bottom")
    if close_cols[1].button("Close", width="stretch"):
        st.session_state["show_entry_detail"] = False
        st.rerun()


def _render_entry_detail_contents() -> None:
    rows: List[Dict[str, Any]] = st.session_state.get("rows", [])
    schema_fields: List[SchemaField] = st.session_state.get("schema_field_objects", [])
    selected_id = st.session_state.get("selected_row_id", "")

    if not rows:
        st.warning("No results available.")
        return

    row = next((item for item in rows if str(item.get("id", "")) == selected_id), rows[0])
    st.session_state["selected_row_id"] = str(row.get("id", ""))

    row_ids = [str(r.get("id", "")) for r in rows]
    current_idx = next(
        (i for i, rid in enumerate(row_ids) if rid == str(row.get("id", ""))), 0
    )

    nav_cols = st.columns([4, 1, 1])
    nav_cols[0].caption(f"Entry {current_idx + 1} of {len(rows)}")
    if nav_cols[1].button("‹ Prev", disabled=current_idx == 0, width="stretch"):
        st.session_state["selected_row_id"] = row_ids[current_idx - 1]
        st.rerun()
    if nav_cols[2].button("Next ›", disabled=current_idx >= len(rows) - 1, width="stretch"):
        st.session_state["selected_row_id"] = row_ids[current_idx + 1]
        st.rerun()

    confidence = row.get("confidence")
    if confidence is not None:
        try:
            st.metric("Confidence", f"{float(confidence):.2f}")
        except (ValueError, TypeError):
            pass

    st.text_area("Raw Text", value=str(row.get("raw_text", "")), height=180, disabled=True)

    for field in schema_fields:
        key = f"detail_{row.get('id')}_{field.name}"
        current_value = row.get(field.name)

        if field.type == "number":
            numeric_value = float(current_value) if isinstance(current_value, (int, float)) else 0.0
            st.number_input(field.name, value=numeric_value, key=key, disabled=True)
        elif field.type == "boolean":
            st.checkbox(field.name, value=bool(current_value), key=key, disabled=True)
        elif field.type == "enum" and field.enum:
            options = list(field.enum)
            current = str(current_value) if current_value in options else options[0]
            st.selectbox(
                field.name,
                options=options,
                index=options.index(current),
                key=key,
                disabled=True,
            )
        else:
            st.text_input(
                field.name,
                value="" if current_value is None else str(current_value),
                key=key,
                disabled=True,
            )


def main() -> None:
    st.set_page_config(page_title="Data Extraction Pipeline", layout="wide")
    st.markdown(
        """
        <style>
        /* Layout */
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}

        /* Radio groups: left-align options */
        div[data-testid="stRadio"] [role="radiogroup"] {justify-content: flex-start;}

        /* Monospace font for raw-text and regex text areas */
        div[data-testid="stTextArea"] textarea {
            font-family: "JetBrains Mono", "Fira Mono", "Consolas", monospace;
            font-size: 13px;
        }

        /* Tighten sidebar nav buttons */
        section[data-testid="stSidebar"] div[data-testid="stButton"] button {
            text-align: left;
            justify-content: flex-start;
        }

        /* Metric card delta — suppress arrow for neutral deltas */
        div[data-testid="stMetricDelta"] svg {display: none;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Data Extraction Pipeline")

    _init_state()
    _render_sidebar()

    # Allow row-level links from Results table to open Entry Detail inline.
    qp_entry = st.query_params.get("entry_id")
    if qp_entry:
        st.session_state["selected_row_id"] = unquote_plus(str(qp_entry))
        st.session_state["show_entry_detail"] = True
        st.session_state["step"] = STEP_RESULTS

    _render_stepper()

    step = st.session_state["step"]
    if step == STEP_UPLOAD:
        _upload_screen()
    elif step == STEP_SCHEMA:
        _schema_screen()
    elif step == STEP_PROCESSING:
        _processing_screen()
    elif step == STEP_INSIGHTS:
        _insights_screen()
    else:
        _results_screen()


if __name__ == "__main__":
    main()
