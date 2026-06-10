from __future__ import annotations

from pixelle_video.storage.resilient_json_store import load_json_with_quarantine, save_json_atomic


def test_load_json_with_quarantine_recovers_from_corrupt_file(tmp_path):
    path = tmp_path / "traces.json"
    path.write_text('{"generation_events": [ { bad json ]', encoding="utf-8")
    payload = load_json_with_quarantine(path, {"generation_events": []})
    assert payload == {"generation_events": []}
    assert not path.exists()
    assert list(tmp_path.glob("traces.json.corrupt.*.bak"))


def test_save_json_atomic_roundtrip(tmp_path):
    path = tmp_path / "traces.json"
    save_json_atomic(path, {"ok": True})
    assert '"ok": true' in path.read_text(encoding="utf-8")
