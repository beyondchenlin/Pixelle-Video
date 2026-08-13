from __future__ import annotations

import os

import pytest

from pixelle_video.utils import process_lifetime


@pytest.mark.skipif(os.name != "nt", reason="Windows job objects are Windows-only")
def test_windows_lifetime_guard_fails_closed_when_job_setup_fails(monkeypatch) -> None:
    def fail_install() -> int:
        raise OSError("simulated job setup failure")

    monkeypatch.setattr(process_lifetime, "_WINDOWS_LIFETIME_JOB_HANDLE", None)
    monkeypatch.setattr(
        process_lifetime,
        "_install_windows_process_tree_guard",
        fail_install,
    )

    with pytest.raises(
        process_lifetime.ProcessLifetimeGuardError,
        match="No service was started",
    ):
        process_lifetime.install_process_tree_lifetime_guard()


@pytest.mark.skipif(os.name != "nt", reason="Windows job objects are Windows-only")
def test_windows_lifetime_guard_installation_is_idempotent(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(process_lifetime, "_WINDOWS_LIFETIME_JOB_HANDLE", None)
    monkeypatch.setattr(
        process_lifetime,
        "_install_windows_process_tree_guard",
        lambda: calls.append("install") or 123,
    )

    process_lifetime.install_process_tree_lifetime_guard()
    process_lifetime.install_process_tree_lifetime_guard()

    assert calls == ["install"]
