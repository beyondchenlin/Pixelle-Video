from pixelle_video.services.asset_bible_import_metadata import (
    mark_imported_asset_bible_customized,
)


def test_mark_imported_asset_bible_customized_preserves_origin_metadata():
    next_payload = {
        "asset_bible_id": "bible_demo",
        "metadata": {"source_kind": "imported", "customized": False},
    }
    existing_payload = {
        "metadata": {
            "source_kind": "imported",
            "origin_preset_id": "builtin_asset_bible_demo",
            "origin_revision": "2026-05-04.1",
            "imported_at": "2026-05-04T00:00:00Z",
            "customized": False,
        }
    }

    result = mark_imported_asset_bible_customized(next_payload, existing_payload)

    assert result["metadata"] == {
        "source_kind": "imported",
        "origin_preset_id": "builtin_asset_bible_demo",
        "origin_revision": "2026-05-04.1",
        "imported_at": "2026-05-04T00:00:00Z",
        "customized": True,
    }


def test_mark_imported_asset_bible_customized_ignores_non_imported_assets():
    next_payload = {
        "asset_bible_id": "bible_demo",
        "metadata": {"source_kind": "user"},
    }
    existing_payload = {
        "metadata": {"source_kind": "user", "customized": False},
    }

    result = mark_imported_asset_bible_customized(next_payload, existing_payload)

    assert result == next_payload
