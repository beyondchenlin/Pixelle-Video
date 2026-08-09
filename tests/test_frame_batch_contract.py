import pytest

from pixelle_video.services.frame_batch_contract import (
    FrameBatchContractError,
    extract_frame_batch_records,
    parse_frame_batch_response,
)


def test_parse_frame_batch_response_accepts_bare_single_frame_object():
    records = parse_frame_batch_response(
        {"frame_id": "f1", "visual_task": "explain"},
        primary_key="frame_visual_plans",
        expected_frame_ids=("f1",),
        stage="test",
    )

    assert records == ({"frame_id": "f1", "visual_task": "explain"},)


def test_parse_frame_batch_response_reorders_exact_coverage():
    records = parse_frame_batch_response(
        {"frame_visual_plans": [{"frame_id": "f2"}, {"frame_id": "f1"}]},
        primary_key="frame_visual_plans",
        expected_frame_ids=("f1", "f2"),
        stage="test",
    )

    assert [record["frame_id"] for record in records] == ["f1", "f2"]


def test_parse_frame_batch_response_accepts_frame_keyed_mapping():
    records = parse_frame_batch_response(
        {"f2": {"visual_task": "two"}, "f1": {"visual_task": "one"}},
        primary_key="frame_visual_plans",
        expected_frame_ids=("f1", "f2"),
        stage="test",
    )

    assert records == (
        {"visual_task": "one", "frame_id": "f1"},
        {"visual_task": "two", "frame_id": "f2"},
    )


@pytest.mark.parametrize(
    ("response", "error_code"),
    [
        ({"frame_visual_plans": []}, "frame_coverage_mismatch"),
        (
            {"frame_visual_plans": [{"frame_id": "f1"}, {"frame_id": "f1"}]},
            "duplicate_frame_id",
        ),
        (
            {"frame_visual_plans": [{"frame_id": "f1"}, {"frame_id": "foreign"}]},
            "frame_coverage_mismatch",
        ),
        (
            {"frame_visual_plans": [{"frame_id": "f1"}, "not-a-record"]},
            "non_mapping_frame_record",
        ),
        ({"unexpected": []}, "missing_frame_collection"),
    ],
)
def test_parse_frame_batch_response_rejects_contract_violations(response, error_code):
    with pytest.raises(FrameBatchContractError) as exc_info:
        parse_frame_batch_response(
            response,
            primary_key="frame_visual_plans",
            expected_frame_ids=("f1", "f2"),
            stage="test",
        )

    assert exc_info.value.code == error_code


def test_explicit_empty_primary_collection_does_not_fall_through_to_alias():
    response = {
        "frame_visual_plans": [],
        "items": [{"frame_id": "f1"}],
    }

    with pytest.raises(FrameBatchContractError) as exc_info:
        parse_frame_batch_response(
            response,
            primary_key="frame_visual_plans",
            expected_frame_ids=("f1",),
            stage="test",
        )

    assert exc_info.value.code == "frame_coverage_mismatch"


def test_extract_frame_batch_records_preserves_legacy_aliases():
    assert extract_frame_batch_records(
        {"data": [{"frame_id": "f1"}]},
        primary_key="frame_visual_plans",
        stage="test",
    ) == ({"frame_id": "f1"},)
