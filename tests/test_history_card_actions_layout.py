from pathlib import Path


def test_history_card_actions_use_scoped_centered_action_band():
    history_page = next((Path(__file__).resolve().parents[1] / "web" / "pages").glob("*History.py"))
    source = history_page.read_text(encoding="utf-8")

    assert "def build_history_page_css()" in source
    assert 'div[class*="st-key-history_card_actions_"] div[data-testid="stHorizontalBlock"]' in source
    assert "width: min(12rem, 82%)" in source
    assert "margin-inline: auto" in source
    assert "justify-content: space-between" in source
    assert "flex: 0 0 auto !important" in source
    assert 'st.container(key=f"history_card_actions_{task_id}")' in source
    assert "st.markdown(build_history_page_css(), unsafe_allow_html=True)" in source
