from web.home_dashboard import (
    increase_dashboard_visible_count,
    normalize_dashboard_visible_count,
    reset_dashboard_visible_count,
    resolve_dashboard_warmup_target,
)


def test_normalize_visible_count_recovers_from_invalid_session_state():
    assert normalize_dashboard_visible_count(None) == 24
    assert normalize_dashboard_visible_count(True) == 24
    assert normalize_dashboard_visible_count("corrupted") == 24
    assert normalize_dashboard_visible_count(-9) == 24
    assert normalize_dashboard_visible_count("48") == 48
    assert normalize_dashboard_visible_count(50_000) == 50_000


def test_increase_visible_count_appends_a_bounded_batch():
    state = {"visible": "corrupted"}

    increase_dashboard_visible_count(state, state_key="visible")
    assert state["visible"] == 48

    state["visible"] = 9_990
    increase_dashboard_visible_count(state, state_key="visible")
    assert state["visible"] == 10_014


def test_progressive_batches_keep_every_history_item_reachable():
    state = {"visible": 24}

    for _ in range(8):
        increase_dashboard_visible_count(state, state_key="visible")

    assert state["visible"] == 216


def test_visible_count_reset_restores_the_initial_progressive_batch():
    state = {"visible": 240}

    reset_dashboard_visible_count(state, state_key="visible")

    assert state["visible"] == 24


def test_warmup_target_resolution_avoids_preloading_an_unselected_builtin():
    assert resolve_dashboard_warmup_target(None) == "quick_create"
    assert resolve_dashboard_warmup_target("image_to_video") == "image_to_video"
    assert resolve_dashboard_warmup_target("third_party_extension") is None
    assert resolve_dashboard_warmup_target("../../unsafe") is None
