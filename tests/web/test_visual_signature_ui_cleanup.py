from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_standard_style_config_no_longer_renders_duplicate_ip_panel():
    source = (ROOT / "web/components/style_config.py").read_text(encoding="utf-8")

    assert "def render_series_visual_signature_controls()" not in source
    assert "ip_prompt_chain_settings" not in source
    assert "IP 角色融入" not in source
    assert "启用 IP" not in source


def test_user_visible_visual_signature_labels_replace_ip_terms():
    zh = json.loads((ROOT / "web/i18n/locales/zh_CN.json").read_text(encoding="utf-8"))["t"]
    en = json.loads((ROOT / "web/i18n/locales/en_US.json").read_text(encoding="utf-8"))["t"]

    assert zh["content.ip_world.section_title"] == "系列视觉识别"
    assert zh["content.ip_world.enabled"] == "启用视觉签名"
    assert "IP" not in zh["content.ip_world.section_title"]
    assert "IP" not in zh["content.ip_world.enabled"]
    assert "IP" not in zh["content.ip_world.enabled_help"]
    assert "视觉签名" in zh["content.ip_world.ip_profile"]

    assert en["content.ip_world.section_title"] == "Series Visual Identity"
    assert en["content.ip_world.enabled"] == "Enable Visual Signature"
    assert "IP" not in en["content.ip_world.section_title"]
    assert "IP" not in en["content.ip_world.enabled"]
    assert "IP" not in en["content.ip_world.enabled_help"]


def test_visual_signature_navigation_label_replaces_ip_design_title():
    source = (ROOT / "web/app.py").read_text(encoding="utf-8")

    assert 'title="Visual Signature"' in source
    assert 'title="IP Design"' not in source
