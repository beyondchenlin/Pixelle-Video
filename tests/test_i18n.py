import ast
import json
import locale
from pathlib import Path

from pixelle_video.config.storyboard_preset_library import (
    BUILTIN_SHOT_PRESETS,
    BUILTIN_WORLD_PRESETS,
)
from pixelle_video.models.progress import ProgressEvent, ProgressEventType
from web.i18n import detect_system_language, get_language, set_language, tr

REPO_ROOT = Path(__file__).resolve().parents[1]


def _iter_calls(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == name:
            yield node
        elif isinstance(func, ast.Attribute) and func.attr == name:
            yield node


def test_storyboard_builtin_preset_names_translate():
    original_language = get_language()
    try:
        for language in ("zh_CN", "en_US"):
            set_language(language)
            for translation_key in [
                *(preset.display_name_key for preset in BUILTIN_WORLD_PRESETS),
                *(preset.display_name_key for preset in BUILTIN_SHOT_PRESETS),
                *(preset.description_key for preset in BUILTIN_WORLD_PRESETS),
                *(preset.description_key for preset in BUILTIN_SHOT_PRESETS),
            ]:
                translated = tr(translation_key)
                assert translated != translation_key
    finally:
        set_language(original_language)


def test_registered_progress_translations_exist_in_supported_locales():
    from pixelle_video.models.progress import (
        PROGRESS_EVENT_I18N_KEYS,
        PROGRESS_FRAME_ACTION_I18N_KEYS,
    )

    original_language = get_language()
    try:
        for language in ("zh_CN", "en_US"):
            set_language(language)
            for key in [
                *PROGRESS_EVENT_I18N_KEYS.values(),
                *PROGRESS_FRAME_ACTION_I18N_KEYS.values(),
            ]:
                translated = tr(key)
                assert translated != key
    finally:
        set_language(original_language)


def test_standard_progress_emitters_do_not_use_string_event_literals():
    paths = [
        REPO_ROOT / "pixelle_video" / "pipelines" / "standard.py",
        REPO_ROOT / "pixelle_video" / "services" / "frame_processor.py",
    ]

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in _iter_calls(tree, "_report_progress"):
            event_arg = call.args[1]
            assert not isinstance(event_arg, ast.Constant) or not isinstance(event_arg.value, str)

        for call in _iter_calls(tree, "ProgressEvent"):
            for keyword in call.keywords:
                if keyword.arg in {"event_type", "action"}:
                    assert not isinstance(keyword.value, ast.Constant) or not isinstance(
                        keyword.value.value,
                        str,
                    )

        for call in _iter_calls(tree, "_report_staged_frame_progress"):
            for keyword in call.keywords:
                if keyword.arg == "action":
                    assert not isinstance(keyword.value, ast.Constant) or not isinstance(
                        keyword.value.value,
                        str,
                    )


def test_output_preview_formats_progress_events_from_registered_i18n_key(monkeypatch):
    from web.utils import progress_i18n

    calls = []

    def fake_tr(key, **kwargs):
        calls.append(key)
        translations = {
            "progress.generating_storyboard_plan": "生成分镜方案...",
        }
        return translations.get(key, key)

    monkeypatch.setattr(progress_i18n, "tr", fake_tr)

    message = progress_i18n.format_progress_event_message(
        ProgressEvent(event_type=ProgressEventType.GENERATING_STORYBOARD_PLAN, progress=0.08)
    )

    assert message == "生成分镜方案..."
    assert calls == ["progress.generating_storyboard_plan"]


def test_web_progress_formatters_do_not_build_dynamic_progress_i18n_keys():
    paths = [
        REPO_ROOT / "web" / "components" / "output_preview.py",
        REPO_ROOT / "web" / "pipelines" / "asset_based.py",
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "progress.step_{event.action}" not in text
        assert "progress.{event.event_type}" not in text


def test_detect_system_language_maps_windows_chinese_locale_name(monkeypatch):
    monkeypatch.setattr(locale, "getlocale", lambda: ("Chinese (Simplified)_China", "cp936"))

    assert detect_system_language() == "zh_CN"


def test_element_animation_section_label_is_grouped_with_primary_sections():
    locales_dir = Path(__file__).resolve().parents[1] / "web" / "i18n" / "locales"

    for locale_name in ("zh_CN", "en_US"):
        locale_data = json.loads((locales_dir / f"{locale_name}.json").read_text(encoding="utf-8"))
        keys = list(locale_data["t"].keys())

        assert keys.index("section.element_animation") < keys.index("quick_create_flow.title")
        assert locale_data["t"]["section.element_animation"].startswith("\u2728 ")


def test_ip_design_and_apply_translations_exist_in_supported_locales():
    required_keys = [
        "ip_design.page.title",
        "ip_design.page.caption",
        "ip_design.unavailable",
        "ip_design.surface.title",
        "ip_design.surface.caption",
        "ip_design.asset_bible.title",
        "ip_design.asset_bible.select",
        "ip_design.asset_bible.save",
        "ip_design.asset_bible.saved",
        "ip_design.scene_cast.title",
        "ip_design.scene_cast.select",
        "ip_design.scene_cast.save",
        "ip_design.scene_cast.saved",
        "ip_workbench.panel.title",
        "ip_workbench.panel.help",
        "ip_workbench.panel.apply",
        "ip_workbench.panel.apply_success",
    ]
    original_language = get_language()
    try:
        for language in ("zh_CN", "en_US"):
            set_language(language)
            for key in required_keys:
                assert tr(key) != key
    finally:
        set_language(original_language)
