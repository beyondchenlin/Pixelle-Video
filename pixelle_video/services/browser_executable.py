from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class BrowserExecutableError(RuntimeError):
    """Raised when no usable Chromium-family executable can be resolved."""


@dataclass(frozen=True)
class BrowserExecutable:
    path: Path
    source: str


_EXPLICIT_BROWSER_ENV_VARS = (
    "PIXELLE_BROWSER_EXECUTABLE",
    "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH",
    "PUPPETEER_EXECUTABLE_PATH",
    "PRODUCER_HEADLESS_SHELL_PATH",
    "PRODUCER_CHROME_PATH",
)


def resolve_browser_executable(
    browser_type: Any,
    *,
    environment: Mapping[str, str] | None = None,
    home_directory: str | Path | None = None,
) -> BrowserExecutable:
    """Resolve one deterministic browser executable for Playwright callers.

    Resolution order is explicit override, Playwright's pinned browser,
    Puppeteer's pinned cache, then a system installation. An invalid explicit
    override is rejected instead of silently changing browser versions.
    """

    env = os.environ if environment is None else environment
    for variable_name in _EXPLICIT_BROWSER_ENV_VARS:
        configured_path = str(env.get(variable_name, "")).strip()
        if not configured_path:
            continue
        path = Path(configured_path).expanduser()
        if not path.is_file():
            raise BrowserExecutableError(
                f"Configured browser executable does not exist: {variable_name}={path}"
            )
        return BrowserExecutable(path=path.resolve(), source=f"environment:{variable_name}")

    playwright_path = _playwright_executable_path(browser_type)
    if playwright_path is not None and playwright_path.is_file():
        return BrowserExecutable(path=playwright_path.resolve(), source="playwright")

    home = Path(home_directory).expanduser() if home_directory is not None else Path.home()
    for candidate in _puppeteer_cache_candidates(home):
        if candidate.is_file():
            return BrowserExecutable(path=candidate.resolve(), source="puppeteer-cache")

    for candidate in _system_browser_candidates(env):
        if candidate.is_file():
            return BrowserExecutable(path=candidate.resolve(), source="system")

    searched = ", ".join(_EXPLICIT_BROWSER_ENV_VARS)
    raise BrowserExecutableError(
        "No usable Chromium-family browser executable was found. Install the Playwright "
        "Chromium browser, install the HyperFrames bridge dependencies, install Chrome/Edge, "
        f"or configure one of: {searched}."
    )


def browser_launch_args(environment: Mapping[str, str] | None = None) -> list[str]:
    """Return hardened, cross-platform launch arguments for local rendering."""

    env = os.environ if environment is None else environment
    args = ["--disable-extensions", "--disable-gpu"]
    if os.name != "nt":
        args.append("--disable-dev-shm-usage")
    if str(env.get("PIXELLE_BROWSER_DISABLE_SANDBOX", "")).strip() == "1":
        args.append("--no-sandbox")
    return args


def _playwright_executable_path(browser_type: Any) -> Path | None:
    value = getattr(browser_type, "executable_path", None)
    if callable(value):
        value = value()
    normalized = str(value or "").strip()
    return Path(normalized).expanduser() if normalized else None


def _puppeteer_cache_candidates(home: Path) -> list[Path]:
    cache_root = home / ".cache" / "puppeteer"
    patterns = (
        "chrome/*/chrome-win64/chrome.exe",
        "chrome/*/chrome-win/chrome.exe",
        "chrome/*/chrome-linux64/chrome",
        "chrome/*/chrome-linux/chrome",
        "chrome/*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chrome-headless-shell/*/chrome-headless-shell-win64/chrome-headless-shell.exe",
        "chrome-headless-shell/*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chrome-headless-shell/*/chrome-headless-shell-mac-arm64/chrome-headless-shell",
        "chrome-headless-shell/*/chrome-headless-shell-mac-x64/chrome-headless-shell",
    )
    candidates = [candidate for pattern in patterns for candidate in cache_root.glob(pattern)]
    return sorted(candidates, key=_browser_version_key, reverse=True)


def _browser_version_key(path: Path) -> tuple[int, ...]:
    for parent in path.parents:
        if re.search(r"\d+\.\d+", parent.name):
            return tuple(int(part) for part in re.findall(r"\d+", parent.name))
    return ()


def _system_browser_candidates(environment: Mapping[str, str]) -> list[Path]:
    candidates: list[Path] = []
    if os.name == "nt":
        roots = [
            environment.get("PROGRAMFILES"),
            environment.get("PROGRAMFILES(X86)"),
            environment.get("LOCALAPPDATA"),
        ]
        relative_paths = (
            "Google/Chrome/Application/chrome.exe",
            "Microsoft/Edge/Application/msedge.exe",
            "Chromium/Application/chrome.exe",
        )
        candidates.extend(
            Path(root) / relative_path
            for root in roots
            if root
            for relative_path in relative_paths
        )
        executable_names = ("chrome.exe", "msedge.exe", "chromium.exe")
    elif sys.platform == "darwin":
        candidates.extend(
            [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            ]
        )
        executable_names = ("google-chrome", "microsoft-edge", "chromium")
    else:
        executable_names = (
            "google-chrome-stable",
            "google-chrome",
            "microsoft-edge-stable",
            "microsoft-edge",
            "chromium",
            "chromium-browser",
        )

    search_path = environment.get("PATH")
    for executable_name in executable_names:
        resolved = shutil.which(executable_name, path=search_path) if search_path else None
        if resolved:
            candidates.append(Path(resolved))
    return candidates
