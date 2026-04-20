from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .errors import DepipelineError


SUPPORTED_FIELD_TYPES = {"string", "number", "boolean", "enum"}


@dataclass(frozen=True)
class SchemaField:
    name: str
    type: str
    enum: List[str] | None = None
    description: str | None = None


class SchemaError(DepipelineError):
    pass


def load_schema_file(path: str | Path) -> List[SchemaField]:
    schema_path = Path(path)
    if not schema_path.exists():
        raise SchemaError(f"Schema file not found: {schema_path}")

    try:
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SchemaError(f"Failed parsing schema JSON: {schema_path}") from exc

    if isinstance(payload, dict) and "fields" in payload:
        fields_obj = payload["fields"]
    else:
        fields_obj = payload

    if not isinstance(fields_obj, list):
        raise SchemaError("Schema must be a list of field objects or an object with a 'fields' list")

    return parse_schema_fields(fields_obj)


def parse_schema_fields(fields_obj: Iterable[object]) -> List[SchemaField]:
    fields: List[SchemaField] = []

    for index, raw in enumerate(fields_obj, start=1):
        if not isinstance(raw, dict):
            raise SchemaError(f"Schema field at position {index} must be an object")

        name = str(raw.get("name", "")).strip()
        if not name:
            raise SchemaError(f"Schema field at position {index} is missing a non-empty 'name'")

        field_type = str(raw.get("type", "")).strip().lower()
        if field_type not in SUPPORTED_FIELD_TYPES:
            raise SchemaError(
                f"Field '{name}' has unsupported type '{field_type}'. "
                f"Supported types: {sorted(SUPPORTED_FIELD_TYPES)}"
            )

        enum_values: List[str] | None = None
        if field_type == "enum":
            enum_raw = raw.get("enum")
            if not isinstance(enum_raw, list) or not enum_raw:
                raise SchemaError(f"Enum field '{name}' must provide a non-empty 'enum' list")
            enum_values = [str(item).strip() for item in enum_raw if str(item).strip()]
            if not enum_values:
                raise SchemaError(f"Enum field '{name}' contains no usable enum values")

        description = raw.get("description")
        fields.append(
            SchemaField(
                name=name,
                type=field_type,
                enum=enum_values,
                description=str(description).strip() if description else None,
            )
        )

    if not fields:
        raise SchemaError("Schema must include at least one field")

    return fields