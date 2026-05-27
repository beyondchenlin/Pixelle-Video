from __future__ import annotations

from pathlib import Path


def test_ip_design_page_config_runs_before_session_state_initialization() -> None:
    source = Path("web/pages/3_IP_Design_Workbench.py").read_text(encoding="utf-8")

    page_config_index = source.index("st.set_page_config(")
    init_session_index = source.index("    init_session_state()")
    init_i18n_index = source.index("    init_i18n()")

    assert page_config_index < init_session_index
    assert page_config_index < init_i18n_index
