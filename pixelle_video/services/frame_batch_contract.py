"""Strict boundary contract for frame-batch model responses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.utils.json_parsing import parse_llm_json_response

DEFAULT_FRAME_COLLECTION_ALIASES = (
    "frame_plans",
    "visual_plans",
    "frame_visual_plan",
    "frames",
    "plans",
    "data",
    "items",
)
_FRAME_RESPONSE_WRAPPER_KEYS = ("result", "output", "response")
_MAX_FRAME_RESPONSE_WRAPPER_DEPTH = 4


class FrameBatchContractError(ValueError):
    """A safe, structured error raised when frame-batch data violates its contract."""

    def __init__(self, code: str, stage: str, message: str) -> None:
        self.code = str(code).strip() or "frame_batch_contract_error"
        self.stage = str(stage).strip() or "frame_batch"
        super().__init__(f"{self.stage}: {message}")


def parse_frame_batch_response(
    response: Any,
    *,
    primary_key: str,
    expected_frame_ids: Sequence[str],
    stage: str,
    aliases: Sequence[str] = DEFAULT_FRAME_COLLECTION_ALIASES,
) -> tuple[dict[str, Any], ...]:
    """Parse, validate, and order a model response by the requested frame IDs.

    Accepted shapes are a direct list, a named list wrapper, a mapping keyed by
    frame ID, or a bare single-frame object.  Every accepted response must still
    cover the expected frame IDs exactly once.
    """

    records = extract_frame_batch_records(
        response,
        primary_key=primary_key,
        stage=stage,
        aliases=aliases,
    )
    return validate_frame_batch_coverage(
        records,
        expected_frame_ids=expected_frame_ids,
        stage=stage,
    )


def extract_frame_batch_records(
    response: Any,
    *,
    primary_key: str,
    stage: str,
    aliases: Sequence[str] = DEFAULT_FRAME_COLLECTION_ALIASES,
) -> tuple[dict[str, Any], ...]:
    """Extract records from supported response shapes without applying coverage rules."""

    payload = _coerce_response(response, stage=stage)
    values = _select_collection(
        payload,
        primary_key=primary_key,
        aliases=aliases,
        stage=stage,
    )
    return normalize_frame_records(values, stage=stage)


def normalize_frame_records(values: Any, *, stage: str) -> tuple[dict[str, Any], ...]:
    """Normalize a list or frame-keyed mapping without silently dropping entries."""

    if isinstance(values, Mapping):
        if _has_frame_id(values):
            candidates: Sequence[Any] = (values,)
        else:
            keyed_records: list[dict[str, Any]] = []
            for key, value in values.items():
                if not isinstance(value, Mapping):
                    raise FrameBatchContractError(
                        "non_mapping_frame_record",
                        stage,
                        "frame-keyed collections must contain mapping values",
                    )
                record = dict(value)
                record.setdefault("frame_id", str(key).strip())
                keyed_records.append(record)
            candidates = keyed_records
    elif isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)):
        candidates = values
    else:
        raise FrameBatchContractError(
            "invalid_frame_collection",
            stage,
            "frame collection must be a list, frame-keyed mapping, or single frame object",
        )

    records: list[dict[str, Any]] = []
    for index, value in enumerate(candidates):
        if not isinstance(value, Mapping):
            raise FrameBatchContractError(
                "non_mapping_frame_record",
                stage,
                f"frame record at index {index} must be a mapping",
            )
        record = dict(value)
        frame_id = str(record.get("frame_id") or "").strip()
        if not frame_id:
            raise FrameBatchContractError(
                "missing_frame_id",
                stage,
                f"frame record at index {index} must include frame_id",
            )
        record["frame_id"] = frame_id
        records.append(record)
    return tuple(records)


def validate_frame_batch_coverage(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_frame_ids: Sequence[str],
    stage: str,
) -> tuple[dict[str, Any], ...]:
    """Require exact, duplicate-free coverage and return records in request order."""

    expected = _normalized_expected_ids(expected_frame_ids, stage=stage)
    normalized = normalize_frame_records(records, stage=stage)
    received_ids = tuple(record["frame_id"] for record in normalized)
    duplicate_ids = _duplicates(received_ids)
    if duplicate_ids:
        raise FrameBatchContractError(
            "duplicate_frame_id",
            stage,
            f"frame IDs must be unique; duplicates={_safe_ids(duplicate_ids)}",
        )

    expected_set = set(expected)
    received_set = set(received_ids)
    missing = tuple(frame_id for frame_id in expected if frame_id not in received_set)
    unexpected = tuple(frame_id for frame_id in received_ids if frame_id not in expected_set)
    if missing or unexpected:
        raise FrameBatchContractError(
            "frame_coverage_mismatch",
            stage,
            "frame coverage must match the request exactly; "
            f"missing={_safe_ids(missing)}, unexpected={_safe_ids(unexpected)}",
        )

    by_frame_id = {record["frame_id"]: dict(record) for record in normalized}
    return tuple(by_frame_id[frame_id] for frame_id in expected)


def frame_ids_from_records(records: Sequence[Mapping[str, Any]], *, stage: str) -> tuple[str, ...]:
    """Validate caller-owned frame records and return their unique IDs."""

    normalized = normalize_frame_records(records, stage=stage)
    frame_ids = tuple(record["frame_id"] for record in normalized)
    duplicate_ids = _duplicates(frame_ids)
    if duplicate_ids:
        raise FrameBatchContractError(
            "duplicate_frame_id",
            stage,
            f"frame IDs must be unique; duplicates={_safe_ids(duplicate_ids)}",
        )
    if not frame_ids:
        raise FrameBatchContractError(
            "empty_frame_batch",
            stage,
            "frame batch must contain at least one frame",
        )
    return frame_ids


def _coerce_response(response: Any, *, stage: str) -> Any:
    if hasattr(response, "model_dump"):
        response = response.model_dump(mode="json")
    elif isinstance(response, str):
        response = parse_llm_json_response(
            response.strip(),
            allow_code_fence=True,
            allow_embedded_json=False,
        )
    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, Sequence) and not isinstance(response, (str, bytes, bytearray)):
        return response
    raise FrameBatchContractError(
        "invalid_response_type",
        stage,
        "model response must be a mapping or list",
    )


def _select_collection(
    payload: Any,
    *,
    primary_key: str,
    aliases: Sequence[str],
    stage: str,
    depth: int = 0,
) -> Any:
    if not isinstance(payload, Mapping):
        return payload
    if primary_key in payload:
        return payload[primary_key]
    for alias in aliases:
        if alias in payload:
            candidate = payload[alias]
            if (
                alias == "data"
                and depth < _MAX_FRAME_RESPONSE_WRAPPER_DEPTH
                and isinstance(candidate, Mapping)
            ):
                return _select_collection(
                    candidate,
                    primary_key=primary_key,
                    aliases=aliases,
                    stage=stage,
                    depth=depth + 1,
                )
            return candidate
    if depth < _MAX_FRAME_RESPONSE_WRAPPER_DEPTH:
        for wrapper_key in _FRAME_RESPONSE_WRAPPER_KEYS:
            candidate = payload.get(wrapper_key)
            if isinstance(candidate, Mapping | Sequence) and not isinstance(
                candidate,
                str | bytes | bytearray,
            ):
                return _select_collection(
                    candidate,
                    primary_key=primary_key,
                    aliases=aliases,
                    stage=stage,
                    depth=depth + 1,
                )
    if _has_frame_id(payload):
        return payload
    if payload and all(isinstance(value, Mapping) for value in payload.values()):
        return payload
    raise FrameBatchContractError(
        "missing_frame_collection",
        stage,
        f"model response must include {primary_key} or a supported collection alias",
    )


def _has_frame_id(value: Mapping[str, Any]) -> bool:
    return bool(str(value.get("frame_id") or "").strip())


def _normalized_expected_ids(expected_frame_ids: Sequence[str], *, stage: str) -> tuple[str, ...]:
    expected = tuple(str(value or "").strip() for value in expected_frame_ids)
    if not expected or any(not frame_id for frame_id in expected):
        raise FrameBatchContractError(
            "invalid_expected_frame_ids",
            stage,
            "expected frame IDs must be non-empty strings",
        )
    duplicate_ids = _duplicates(expected)
    if duplicate_ids:
        raise FrameBatchContractError(
            "duplicate_expected_frame_id",
            stage,
            f"expected frame IDs must be unique; duplicates={_safe_ids(duplicate_ids)}",
        )
    return expected


def _duplicates(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return tuple(duplicates)


def _safe_ids(values: Sequence[str]) -> str:
    limited = [str(value)[:120] for value in values[:20]]
    if len(values) > len(limited):
        limited.append("...")
    return repr(limited)


__all__ = [
    "DEFAULT_FRAME_COLLECTION_ALIASES",
    "FrameBatchContractError",
    "extract_frame_batch_records",
    "frame_ids_from_records",
    "normalize_frame_records",
    "parse_frame_batch_response",
    "validate_frame_batch_coverage",
]
