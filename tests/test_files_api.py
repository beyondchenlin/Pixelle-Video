from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routers.files import get_file


@pytest.mark.asyncio
async def test_get_file_rejects_output_path_traversal(monkeypatch, tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "config.yaml").write_text("secret: value", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await get_file("output/../config.yaml")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_file_allows_file_inside_output(monkeypatch, tmp_path):
    video = tmp_path / "output" / "task-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    monkeypatch.chdir(tmp_path)

    response = await get_file("task-1/final.mp4")

    assert Path(response.path) == video
