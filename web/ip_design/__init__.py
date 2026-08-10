from __future__ import annotations

import typing

from web.ip_design.models import (
    AssetBibleDraft,
    AssetBibleSummary,
    CharacterProfileDraft,
    DeleteResponse,
    FieldId,
    ImportPresetResponse,
    IPProfileDraft,
    ListAssetBiblesResponse,
    ListPresetsResponse,
    ListSceneCastsResponse,
    PresetSummary,
    PropAssetDraft,
    ReadinessReport,
    SaveResponse,
    SceneAssetDraft,
    SceneCastDraft,
    StyleProfileDraft,
    TypedResponse,
)
from web.ip_design.session_keys import IPSessionKeys

_LAZY_IMPORTS: dict[str, typing.Any] = {}


def __getattr__(name: str) -> typing.Any:
    lazy = _LAZY_IMPORTS.get(name)
    if lazy is not None:
        return lazy
    if name in ("IPDesignClient", "IPDesignClientError"):
        from web.ip_design.client import IPDesignClient, IPDesignClientError
        _LAZY_IMPORTS["IPDesignClient"] = IPDesignClient
        _LAZY_IMPORTS["IPDesignClientError"] = IPDesignClientError
        return _LAZY_IMPORTS[name]
    if name == "HttpIPDesignClient":
        from web.ip_design.http_client import HttpIPDesignClient
        _LAZY_IMPORTS["HttpIPDesignClient"] = HttpIPDesignClient
        return HttpIPDesignClient
    if name == "InProcessIPDesignClient":
        from web.ip_design.inprocess_client import InProcessIPDesignClient
        _LAZY_IMPORTS["InProcessIPDesignClient"] = InProcessIPDesignClient
        return InProcessIPDesignClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "HttpIPDesignClient",
    "InProcessIPDesignClient",
    "IPDesignClient",
    "IPDesignClientError",
    "IPSessionKeys",
    "TypedResponse",
    "AssetBibleSummary",
    "PresetSummary",
    "AssetBibleDraft",
    "IPProfileDraft",
    "CharacterProfileDraft",
    "SceneAssetDraft",
    "PropAssetDraft",
    "StyleProfileDraft",
    "SceneCastDraft",
    "FieldId",
    "SaveResponse",
    "DeleteResponse",
    "ListAssetBiblesResponse",
    "ListSceneCastsResponse",
    "ListPresetsResponse",
    "ImportPresetResponse",
    "ReadinessReport",
]
