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
