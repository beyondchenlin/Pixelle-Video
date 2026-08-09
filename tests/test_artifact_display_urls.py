import pytest


def test_artifact_display_url_keeps_absolute_http_url():
    from web.utils.artifact_display_urls import artifact_url_for_streamlit

    assert (
        artifact_url_for_streamlit(
            "https://cdn.pixelle.test/artifacts/frame.png",
            api_base_url="http://localhost:6789/api",
        )
        == "https://cdn.pixelle.test/artifacts/frame.png"
    )


def test_artifact_display_url_resolves_controlled_relative_url_against_api_origin():
    from web.utils.artifact_display_urls import artifact_url_for_streamlit

    assert (
        artifact_url_for_streamlit(
            "/api/files/artifacts/workspace_1/frame.png",
            api_base_url="http://localhost:6789/api",
        )
        == "http://localhost:6789/api/files/artifacts/workspace_1/frame.png"
    )


def test_artifact_display_url_rejects_local_paths():
    from web.utils.artifact_display_urls import artifact_url_for_streamlit

    with pytest.raises(ValueError, match="artifact access URL"):
        artifact_url_for_streamlit(
            r"D:\output\frame.png",
            api_base_url="http://localhost:6789/api",
        )


def test_artifact_display_url_requires_absolute_api_base_for_relative_urls():
    from web.utils.artifact_display_urls import artifact_url_for_streamlit

    with pytest.raises(ValueError, match="api_base_url"):
        artifact_url_for_streamlit(
            "/api/files/artifacts/workspace_1/frame.png",
            api_base_url="/api",
        )
