from web.utils.streamlit_helpers import (
    keyed_widget_default_kwargs,
    normalize_keyed_option,
    session_state_has_key,
)


def test_keyed_widget_default_kwargs_omits_defaults_when_session_key_exists():
    session_state = {"demo": "stored"}

    kwargs = keyed_widget_default_kwargs(session_state, "demo", value="fallback")

    assert kwargs == {}


def test_keyed_widget_default_kwargs_keeps_defaults_when_session_key_is_absent():
    session_state = {}

    kwargs = keyed_widget_default_kwargs(session_state, "demo", value="fallback")

    assert kwargs == {"value": "fallback"}


def test_normalize_keyed_option_updates_invalid_existing_session_value():
    session_state = {"mode": "stale"}

    value, has_session_value = normalize_keyed_option(
        session_state,
        "mode",
        options=["auto", "manual"],
        default="auto",
    )

    assert value == "auto"
    assert has_session_value is True
    assert session_state["mode"] == "auto"


def test_session_state_has_key_handles_plain_objects_without_membership():
    class PlainSessionState:
        pass

    assert session_state_has_key(PlainSessionState(), "demo") is False


# ── New helper function tests ──

def test_first_text_returns_first_non_empty():
    from web.utils.streamlit_helpers import first_text
    assert first_text(None, "", "hello", "world") == "hello"


def test_first_text_returns_empty_when_all_empty():
    from web.utils.streamlit_helpers import first_text
    assert first_text(None, "", "  ") == ""


def test_first_text_returns_single_value():
    from web.utils.streamlit_helpers import first_text
    assert first_text("hello") == "hello"


def test_first_text_handles_none():
    from web.utils.streamlit_helpers import first_text
    assert first_text(None) == ""


def test_list_of_dicts_filters_non_dicts():
    from web.utils.streamlit_helpers import list_of_dicts
    result = list_of_dicts([{"a": 1}, "string", None, {"b": 2}])
    assert result == [{"a": 1}, {"b": 2}]


def test_list_of_dicts_returns_empty_for_non_list():
    from web.utils.streamlit_helpers import list_of_dicts
    assert list_of_dicts("not a list") == []
    assert list_of_dicts(None) == []


def test_list_of_dicts_empty_input():
    from web.utils.streamlit_helpers import list_of_dicts
    assert list_of_dicts([]) == []


def test_text_list_filters_empty():
    from web.utils.streamlit_helpers import text_list
    result = text_list(["hello", "", "world", None, "  "])
    assert result == ["hello", "world"]


def test_text_list_non_list_input():
    from web.utils.streamlit_helpers import text_list
    assert text_list(None) == []


def test_split_csv_normal():
    from web.utils.streamlit_helpers import split_csv
    assert split_csv("a, b, c") == ["a", "b", "c"]


def test_split_csv_empty():
    from web.utils.streamlit_helpers import split_csv
    assert split_csv("") == []


def test_split_csv_single():
    from web.utils.streamlit_helpers import split_csv
    assert split_csv("hello") == ["hello"]


def test_find_item_finds_existing():
    from web.utils.streamlit_helpers import find_item
    items = [{"id": "a", "name": "Alice"}, {"id": "b", "name": "Bob"}]
    result = find_item(items, "id", "b")
    assert result == {"id": "b", "name": "Bob"}


def test_find_item_returns_none_when_not_found():
    from web.utils.streamlit_helpers import find_item
    items = [{"id": "a"}]
    result = find_item(items, "id", "z")
    assert result is None


def test_find_item_empty_list():
    from web.utils.streamlit_helpers import find_item
    assert find_item([], "id", "a") is None
