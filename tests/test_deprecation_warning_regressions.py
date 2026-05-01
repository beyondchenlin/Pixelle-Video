import importlib
import warnings

SCHEMA_MODULES = [
    "api.schemas.llm",
    "api.schemas.tts",
    "api.schemas.image",
    "api.schemas.frame",
    "api.schemas.content",
    "api.schemas.video",
    "api.tasks.models",
]


def test_api_schema_modules_reload_without_pydantic_v2_deprecation_warnings():
    caught = []
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        for module_name in SCHEMA_MODULES:
            module = importlib.import_module(module_name)
            importlib.reload(module)
        caught.extend(records)

    deprecations = [
        warning
        for warning in caught
        if "PydanticDeprecatedSince20" in warning.category.__name__
    ]
    assert not deprecations


def test_i18n_reload_without_getdefaultlocale_deprecation_warning():
    module = importlib.import_module("web.i18n")

    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        importlib.reload(module)

    locale_deprecations = [
        warning
        for warning in records
        if "getdefaultlocale" in str(warning.message)
    ]
    assert not locale_deprecations
