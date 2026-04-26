import web.components.tts_voice_profile_controls as controls


class _FakeUpload:
    name = "sample.wav"


class _FakeStreamlit:
    def __init__(self):
        self.success_calls = []
        self.warning_calls = []
        self.audio_calls = []
        self.session_state = {}
        self.selectbox_result = None
        self.text_area_result = ""
        self.text_input_result = ""
        self.file_uploader_result = None
        self.button_result = False

    def selectbox(self, _label, options, **_kwargs):
        if self.selectbox_result is not None:
            return self.selectbox_result
        return options[0]

    def text_area(self, _label, value="", **_kwargs):
        return self.text_area_result if self.text_area_result else value

    def file_uploader(self, *_args, **_kwargs):
        return self.file_uploader_result

    def text_input(self, *_args, **_kwargs):
        return self.text_input_result

    def button(self, *_args, **_kwargs):
        return self.button_result

    def audio(self, value, **_kwargs):
        self.audio_calls.append(value)

    def success(self, value, **_kwargs):
        self.success_calls.append(value)

    def warning(self, value, **_kwargs):
        self.warning_calls.append(value)


def test_voice_profile_controls_return_selected_saved_profile(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.selectbox_result = "陈林-indextts2"
    fake_st.text_area_result = "新的参考文本"
    monkeypatch.setattr(controls, "st", fake_st)
    monkeypatch.setattr(
        controls, "tr", lambda key, **kwargs: key.format(**kwargs) if kwargs else key
    )
    monkeypatch.setattr(
        controls,
        "list_voice_profiles",
        lambda workflow_key: [
            {
                "name": "陈林-indextts2",
                "audio_path": "data/reference_audio/indextts2/陈林-indextts2.wav",
                "ref_audio_text": "旧文本",
            }
        ],
    )

    ref_audio_path, ref_audio_text = controls.render_tts_voice_profile_controls(
        "selfhost/tts_index2.json",
    )

    assert ref_audio_path == "data/reference_audio/indextts2/陈林-indextts2.wav"
    assert ref_audio_text == "新的参考文本"


def test_voice_profile_controls_save_uploaded_profile(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.file_uploader_result = _FakeUpload()
    fake_st.text_input_result = "陈林"
    fake_st.text_area_result = "参考文本"
    fake_st.button_result = True
    monkeypatch.setattr(controls, "st", fake_st)
    monkeypatch.setattr(
        controls, "tr", lambda key, **kwargs: key.format(**kwargs) if kwargs else key
    )
    monkeypatch.setattr(controls, "list_voice_profiles", lambda workflow_key: [])

    captured = {}

    def _save_voice_profile(**kwargs):
        captured.update(kwargs)
        return {
            "name": "陈林-indextts2",
            "audio_path": "data/reference_audio/indextts2/陈林-indextts2.wav",
            "ref_audio_text": kwargs["ref_audio_text"],
        }

    monkeypatch.setattr(controls, "save_voice_profile", _save_voice_profile)

    ref_audio_path, ref_audio_text = controls.render_tts_voice_profile_controls(
        "selfhost/tts_index2.json",
    )

    assert captured["upload"] is fake_st.file_uploader_result
    assert captured["base_name"] == "陈林"
    assert captured["workflow_key"] == "selfhost/tts_index2.json"
    assert captured["ref_audio_text"] == "参考文本"
    assert ref_audio_path == "data/reference_audio/indextts2/陈林-indextts2.wav"
    assert ref_audio_text == "参考文本"
    assert fake_st.success_calls == ["tts.voice_profile_saved"]
