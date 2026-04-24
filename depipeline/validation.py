from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .schema import SchemaField


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: List[ValidationIssue]
    missing_fields: int
    type_coercions: int


def validate_model_object(model_obj: Dict[str, object], schema_fields: List[SchemaField]) -> ValidationResult:
    issues: List[ValidationIssue] = []
    missing_fields = 0
    type_coercions = 0

    schema_names = {field.name for field in schema_fields}

    for key in model_obj.keys():
        if key not in schema_names:
            issues.append(
                ValidationIssue(
                    field=key,
                    code="extra_key",
                    message=f"Unexpected key '{key}' is not in schema",
                )
            )

    for field in schema_fields:
        if field.name not in model_obj:
            missing_fields += 1
            issues.append(
                ValidationIssue(
                    field=field.name,
                    code="missing_key",
                    message=f"Missing required schema key '{field.name}'",
                )
            )
            continue

        value = model_obj.get(field.name)
        if value is None:
            missing_fields += 1
            continue

        valid, coercion_needed = _check_value(field, value)
        if coercion_needed:
            type_coercions += 1
        if not valid:
            issues.append(
                ValidationIssue(
                    field=field.name,
                    code="invalid_type_or_value",
                    message=_invalid_message(field, value),
                )
            )

    return ValidationResult(
        valid=len(issues) == 0,
        issues=issues,
        missing_fields=missing_fields,
        type_coercions=type_coercions,
    )


def _check_value(field: SchemaField, value: object) -> tuple[bool, bool]:
    if field.type == "string":
        return True, not isinstance(value, str)

    if field.type == "number":
        if isinstance(value, bool):
            return False, False
        if isinstance(value, (int, float)):
            return True, False
        if isinstance(value, str):
            text = value.strip().replace(",", "")
            if not text:
                return False, False
            try:
                float(text)
                return True, True
            except ValueError:
                return False, False
        return False, False

    if field.type == "boolean":
        if isinstance(value, bool):
            return True, False
        if isinstance(value, (int, float)) and value in {0, 1}:
            return True, True
        if isinstance(value, str):
            if value.strip().lower() in {"true", "false", "yes", "no", "y", "n", "1", "0"}:
                return True, True
        return False, False

    if field.type == "enum":
        if not isinstance(value, str):
            return False, False
        if not field.enum:
            return False, False
        normalized = value.strip()
        if not normalized:
            return False, False
        by_lower = {option.lower(): option for option in field.enum}
        if normalized.lower() not in by_lower:
            return False, False
        return True, by_lower[normalized.lower()] != normalized

    return False, False


def _invalid_message(field: SchemaField, value: object) -> str:
    if field.type == "enum" and field.enum:
        return (
            f"Field '{field.name}' must be one of {field.enum}; got {value!r}"
        )
    return f"Field '{field.name}' expects type '{field.type}'; got {value!r}"
