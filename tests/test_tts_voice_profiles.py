import json
from pathlib import Path

import pytest

from pixelle_video.services import tts_voice_profiles


class _FakeUpload:
    def __init__(self, name="voice sample.wav", data=b"audio-bytes"):
        self.name = name
        self.data = data

    def getbuffer(self):
        return self.data


def test_build_voice_profile_name_appends_model_suffix():
    assert (
        tts_voice_profiles.build_voice_profile_name("班哥", "selfhost/tts_index2.json")
        == "班哥-indextts2"
    )
    assert (
        tts_voice_profiles.build_voice_profile_name("班哥", "selfhost/tts_voxcpm2_saganaki.json")
        == "班哥-voxcpm2"
    )
    assert (
        tts_voice_profiles.build_voice_profile_name("班哥-indextts2", "selfhost/tts_index2.json")
        == "班哥-indextts2"
    )


def test_save_voice_profile_writes_audio_and_manifest(tmp_path):
    profile = tts_voice_profiles.save_voice_profile(
        upload=_FakeUpload(),
        base_name="班哥",
        workflow_key="selfhost/tts_index2.json",
        ref_audio_text="大家好",
        root_dir=tmp_path / "reference_audio",
        manifest_path=tmp_path / "reference_audio" / "voice_profiles.json",
    )

    assert profile["name"] == "班哥-indextts2"
    assert profile["model_slug"] == "indextts2"
    assert profile["workflow_key"] == "selfhost/tts_index2.json"
    audio_path = tmp_path / profile["audio_path"]
    assert audio_path.read_bytes() == b"audio-bytes"

    manifest = json.loads(
        (tmp_path / "reference_audio" / "voice_profiles.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == 1
    assert manifest["profiles"][0]["name"] == "班哥-indextts2"
    assert manifest["profiles"][0]["ref_audio_text"] == "大家好"


def test_list_voice_profiles_filters_by_tts_model(tmp_path):
    manifest_path = tmp_path / "reference_audio" / "voice_profiles.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    {
                        "id": "a",
                        "name": "班哥-indextts2",
                        "model_slug": "indextts2",
                        "workflow_key": "selfhost/tts_index2.json",
                        "audio_path": "reference_audio/indextts2/bange.wav",
                        "ref_audio_text": "大家好",
                    },
                    {
                        "id": "b",
                        "name": "班哥-voxcpm2",
                        "model_slug": "voxcpm2",
                        "workflow_key": "selfhost/tts_voxcpm2_saganaki.json",
                        "audio_path": "reference_audio/voxcpm2/bange.wav",
                        "ref_audio_text": "",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    profiles = tts_voice_profiles.list_voice_profiles(
        "selfhost/tts_index2.json",
        manifest_path=manifest_path,
    )

    assert [profile["name"] for profile in profiles] == ["班哥-indextts2"]


def test_save_voice_profile_replaces_same_name_for_same_model(tmp_path):
    kwargs = {
        "base_name": "班哥",
        "workflow_key": "selfhost/tts_index2.json",
        "root_dir": tmp_path / "reference_audio",
        "manifest_path": tmp_path / "reference_audio" / "voice_profiles.json",
    }

    first = tts_voice_profiles.save_voice_profile(
        upload=_FakeUpload(),
        ref_audio_text="旧文本",
        **kwargs,
    )
    second = tts_voice_profiles.save_voice_profile(
        upload=_FakeUpload(),
        ref_audio_text="新文本",
        **kwargs,
    )

    assert first["id"] == second["id"]
    assert second["ref_audio_text"] == "新文本"
    manifest = json.loads(Path(kwargs["manifest_path"]).read_text(encoding="utf-8"))
    assert len(manifest["profiles"]) == 1


def test_replacing_voice_profile_removes_previous_audio_file(tmp_path):
    kwargs = {
        "base_name": "班哥",
        "workflow_key": "selfhost/tts_index2.json",
        "root_dir": tmp_path / "reference_audio",
        "manifest_path": tmp_path / "reference_audio" / "voice_profiles.json",
    }

    first = tts_voice_profiles.save_voice_profile(
        upload=_FakeUpload(name="voice.wav"),
        **kwargs,
    )
    old_audio_path = tmp_path / first["audio_path"]
    assert old_audio_path.exists()

    second = tts_voice_profiles.save_voice_profile(
        upload=_FakeUpload(name="voice.mp3", data=b"new-audio"),
        **kwargs,
    )

    assert not old_audio_path.exists()
    assert (tmp_path / second["audio_path"]).read_bytes() == b"new-audio"


def test_save_voice_profile_rejects_non_audio_suffix(tmp_path):
    with pytest.raises(ValueError, match="unsupported reference audio file type"):
        tts_voice_profiles.save_voice_profile(
            upload=_FakeUpload(name="voice.txt"),
            base_name="班哥",
            workflow_key="selfhost/tts_index2.json",
            root_dir=tmp_path / "reference_audio",
            manifest_path=tmp_path / "reference_audio" / "voice_profiles.json",
        )


def test_corrupt_manifest_is_backed_up_before_saving_new_profile(tmp_path):
    root_dir = tmp_path / "reference_audio"
    manifest_path = root_dir / "voice_profiles.json"
    root_dir.mkdir()
    manifest_path.write_text("{not-json", encoding="utf-8")

    profile = tts_voice_profiles.save_voice_profile(
        upload=_FakeUpload(),
        base_name="班哥",
        workflow_key="selfhost/tts_index2.json",
        root_dir=root_dir,
        manifest_path=manifest_path,
    )

    backups = list(root_dir.glob("voice_profiles.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not-json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["profiles"][0]["name"] == profile["name"]
