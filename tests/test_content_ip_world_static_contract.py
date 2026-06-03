from pathlib import Path

FORBIDDEN_FIELDS = (
    "generation_notes",
    "slot_preference_override",
    "presence_strength",
)

CHECKED_FILES = (
    Path("web/components/content_series_visual_signature_controls.py"),
    Path("web/i18n/locales/en_US.json"),
    Path("web/i18n/locales/zh_CN.json"),
)


def test_removed_content_ip_world_fields_do_not_reappear_in_entry_or_i18n():
    for path in CHECKED_FILES:
        text = path.read_text(encoding="utf-8")
        for field in FORBIDDEN_FIELDS:
            assert field not in text, f"{field} reappeared in {path}"
