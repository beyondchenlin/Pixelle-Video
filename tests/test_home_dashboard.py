from web.home_dashboard import (
    change_dashboard_page,
    normalize_dashboard_page,
    resolve_dashboard_warmup_target,
)


def test_normalize_dashboard_page_recovers_from_invalid_session_state():
    assert normalize_dashboard_page(None) == 0
    assert normalize_dashboard_page(True) == 0
    assert normalize_dashboard_page("corrupted") == 0
    assert normalize_dashboard_page(-9) == 0
    assert normalize_dashboard_page("3") == 3


def test_change_dashboard_page_never_moves_before_first_page():
    state = {"page": "corrupted"}

    change_dashboard_page(state, state_key="page", delta=-1)
    assert state["page"] == 0

    change_dashboard_page(state, state_key="page", delta=1)
    assert state["page"] == 1


def test_warmup_target_resolution_avoids_preloading_an_unselected_builtin():
    assert resolve_dashboard_warmup_target(None) == "quick_create"
    assert resolve_dashboard_warmup_target("image_to_video") == "image_to_video"
    assert resolve_dashboard_warmup_target("third_party_extension") is None
    assert resolve_dashboard_warmup_target("../../unsafe") is None
