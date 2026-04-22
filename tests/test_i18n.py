import locale

from web.i18n import detect_system_language, get_language, set_language, tr


def test_rendering_hyperframes_progress_translation_exists_in_supported_locales():
    original_language = get_language()
    try:
        for language in ("zh_CN", "en_US"):
            set_language(language)
            translated = tr("progress.rendering_hyperframes")
            assert translated != "progress.rendering_hyperframes"
    finally:
        set_language(original_language)


def test_detect_system_language_maps_windows_chinese_locale_name(monkeypatch):
    monkeypatch.setattr(locale, "getlocale", lambda: ("Chinese (Simplified)_China", "cp936"))

    assert detect_system_language() == "zh_CN"
