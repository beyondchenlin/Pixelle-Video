import json

import pytest

from pixelle_video.utils.json_parsing import parse_llm_json_response


def test_parse_llm_json_response_accepts_raw_json_object():
    payload = parse_llm_json_response('{"frames": []}')

    assert payload == {"frames": []}


def test_parse_llm_json_response_accepts_markdown_fenced_json():
    payload = parse_llm_json_response(
        """
        ```json
        {"frames": []}
        ```
        """
    )

    assert payload == {"frames": []}


def test_parse_llm_json_response_extracts_embedded_json_when_enabled():
    payload = parse_llm_json_response(
        'Here is the result: {"frames": [], "planner_version": "1.0"}',
        allow_embedded_json=True,
    )

    assert payload == {"frames": [], "planner_version": "1.0"}


def test_parse_llm_json_response_rejects_embedded_json_when_disabled():
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json_response(
            'Here is the result: {"frames": [], "planner_version": "1.0"}',
            allow_embedded_json=False,
        )
