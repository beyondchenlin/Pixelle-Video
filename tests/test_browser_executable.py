import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pixelle_video.services.browser_executable import (
    BrowserExecutableError,
    browser_launch_args,
    resolve_browser_executable,
)


def test_browser_resolution_prefers_valid_explicit_override(tmp_path):
    explicit = tmp_path / "explicit-browser.exe"
    explicit.write_bytes(b"browser")
    bundled = tmp_path / "bundled-browser.exe"
    bundled.write_bytes(b"browser")

    result = resolve_browser_executable(
        SimpleNamespace(executable_path=str(bundled)),
        environment={"PIXELLE_BROWSER_EXECUTABLE": str(explicit)},
        home_directory=tmp_path,
    )

    assert result.path == explicit.resolve()
    assert result.source == "environment:PIXELLE_BROWSER_EXECUTABLE"


def test_browser_resolution_rejects_stale_explicit_override(tmp_path):
    bundled = tmp_path / "bundled-browser.exe"
    bundled.write_bytes(b"browser")

    with pytest.raises(BrowserExecutableError, match="does not exist"):
        resolve_browser_executable(
            SimpleNamespace(executable_path=str(bundled)),
            environment={"PIXELLE_BROWSER_EXECUTABLE": str(tmp_path / "missing.exe")},
            home_directory=tmp_path,
        )


def test_browser_resolution_uses_playwright_before_puppeteer_cache(tmp_path):
    bundled = tmp_path / "bundled-browser.exe"
    bundled.write_bytes(b"browser")
    cached = (
        tmp_path
        / ".cache"
        / "puppeteer"
        / "chrome"
        / "win64-999.0.0.0"
        / "chrome-win64"
        / "chrome.exe"
    )
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"browser")

    result = resolve_browser_executable(
        SimpleNamespace(executable_path=str(bundled)),
        environment={},
        home_directory=tmp_path,
    )

    assert result.path == bundled.resolve()
    assert result.source == "playwright"


def test_browser_resolution_uses_newest_puppeteer_cache_when_playwright_is_missing(tmp_path):
    older = (
        tmp_path
        / ".cache"
        / "puppeteer"
        / "chrome"
        / "win64-120.0.0.0"
        / "chrome-win64"
        / "chrome.exe"
    )
    newer = (
        tmp_path
        / ".cache"
        / "puppeteer"
        / "chrome"
        / "win64-150.0.0.0"
        / "chrome-win64"
        / "chrome.exe"
    )
    for candidate in (older, newer):
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"browser")

    result = resolve_browser_executable(
        SimpleNamespace(executable_path=str(tmp_path / "missing-playwright.exe")),
        environment={},
        home_directory=tmp_path,
    )

    assert result.path == newer.resolve()
    assert result.source == "puppeteer-cache"


def test_browser_launch_keeps_sandbox_enabled_by_default():
    args = browser_launch_args({})

    assert "--no-sandbox" not in args


def test_browser_launch_requires_explicit_sandbox_opt_out():
    args = browser_launch_args({"PIXELLE_BROWSER_DISABLE_SANDBOX": "1"})

    assert "--no-sandbox" in args


def test_browser_resolution_can_use_current_python_as_explicit_test_executable():
    result = resolve_browser_executable(
        SimpleNamespace(executable_path=""),
        environment={"PIXELLE_BROWSER_EXECUTABLE": sys.executable},
        home_directory=Path.cwd(),
    )

    assert result.path.is_file()
    assert result.source.startswith("environment:")
