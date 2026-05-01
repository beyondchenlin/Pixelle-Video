from __future__ import annotations


def validate_public_reference_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    normalized = value.strip()
    if _looks_like_path(normalized):
        raise ValueError(f"{field_name} must be a domain ID, not a local path")
    return normalized


def _looks_like_path(value: str) -> bool:
    return (
        "\\" in value
        or "/" in value
        or ":" in value
        or value in {".", ".."}
        or value.startswith("~")
    )


__all__ = ["validate_public_reference_id"]
