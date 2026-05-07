from __future__ import annotations

from typing import Any


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeUI:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}
        self.markdowns: list[str] = []
        self.captions: list[str] = []
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.successes: list[str] = []
        self.text_inputs: list[dict[str, Any]] = []
        self.text_areas: list[dict[str, Any]] = []
        self.selectboxes: list[dict[str, Any]] = []
        self.buttons: list[dict[str, Any]] = []

    def container(self, **_kwargs):
        return _NoopContext()

    def expander(self, label, **kwargs):
        self.markdowns.append(f"EXPANDER:{label}:{kwargs.get('expanded', False)}")
        return _NoopContext()

    def columns(self, count):
        return [_NoopContext() for _ in range(count)]

    def tabs(self, labels):
        self.markdowns.append("TABS:" + ",".join(labels))
        return [_NoopContext() for _ in labels]

    def markdown(self, message, **_kwargs):
        self.markdowns.append(message)

    def caption(self, message):
        self.captions.append(message)

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)

    def success(self, message):
        self.successes.append(message)

    def text_input(self, label, value="", **kwargs):
        self.text_inputs.append({"label": label, "value": value, **kwargs})
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def text_area(self, label, value="", **kwargs):
        self.text_areas.append({"label": label, "value": value, **kwargs})
        key = kwargs.get("key")
        if key in self.session_state:
            return self.session_state[key]
        return value

    def selectbox(self, label, options, index=0, **kwargs):
        option_list = list(options)
        self.selectboxes.append({"label": label, "options": option_list, "index": index, **kwargs})
        key = kwargs.get("key")
        if key in self.session_state and self.session_state[key] in option_list:
            return self.session_state[key]
        if not option_list:
            return None
        return option_list[index]

    def button(self, label, **kwargs):
        self.buttons.append({"label": label, **kwargs})
        if kwargs.get("disabled"):
            return False
        return bool(self.session_state.get(kwargs.get("key"), False))


class _FakeIPDesignClient:
    def __init__(
        self,
        *,
        asset_bibles: list[dict[str, Any]] | None = None,
        scene_casts: list[dict[str, Any]] | None = None,
        presets: list[dict[str, Any]] | None = None,
    ) -> None:
        self.asset_bibles = asset_bibles or [_asset_bible()]
        self.scene_casts = scene_casts or [_scene_cast()]
        self.presets = presets or []
        self.calls: list[dict[str, Any]] = []
        self.import_calls: list[dict[str, Any]] = []

    def list_asset_bibles(self, **kwargs):
        self.calls.append({"method": "list_asset_bibles", **kwargs})
        return {"success": True, "asset_bibles": self.asset_bibles}

    def load_asset_bible(self, **kwargs):
        self.calls.append({"method": "load_asset_bible", **kwargs})
        return {"success": True, "asset_bible": self.asset_bibles[0]}

    def save_asset_bible(self, **kwargs):
        self.calls.append({"method": "save_asset_bible", **kwargs})
        payload = _asset_bible(asset_bible_id=kwargs["asset_bible_id"])
        payload["ip_profiles"] = kwargs["payload"].get("ip_profiles") or [{}]
        self.asset_bibles = [payload]
        return {"success": True, "asset_bible": payload}

    def list_scene_casts(self, **kwargs):
        self.calls.append({"method": "list_scene_casts", **kwargs})
        return {"success": True, "scene_casts": self.scene_casts}

    def load_scene_cast(self, **kwargs):
        self.calls.append({"method": "load_scene_cast", **kwargs})
        return {"success": True, "scene_cast": self.scene_casts[0]}

    def save_scene_cast(self, **kwargs):
        self.calls.append({"method": "save_scene_cast", **kwargs})
        payload = _scene_cast(scene_cast_id=kwargs["scene_cast_id"])
        payload.update(kwargs["payload"])
        payload["asset_bible_id"] = kwargs["asset_bible_id"]
        self.scene_casts = [payload]
        return {"success": True, "scene_cast": payload}

    def list_asset_bible_presets(self):
        self.calls.append({"method": "list_asset_bible_presets"})
        return list(self.presets)

    def import_asset_bible_preset(self, **kwargs):
        self.import_calls.append(kwargs)
        self.calls.append({"method": "import_asset_bible_preset", **kwargs})
        payload = _asset_bible(
            asset_bible_id=kwargs.get("asset_bible_id") or "demo_bible",
            metadata={"origin_preset_id": kwargs["preset_id"]},
        )
        self.asset_bibles = [payload]
        return {"success": True, "asset_bible": payload}


def _asset_bible(**overrides: Any) -> dict[str, Any]:
    payload = {
        "asset_bible_id": "bible_demo",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "ip_profiles": [
            {
                "ip_profile_id": "ip_main",
                "name": "Pixelle Demo",
                "logline": "A compact character universe.",
                "world_hint": "Floating academy",
                "style_hint": "warm comic",
                "forbidden_elements": ["brand logos"],
            }
        ],
        "character_profiles": [{"character_id": "char_luna", "display_name": "Luna"}],
        "scene_assets": [{"scene_id": "scene_lab", "display_name": "Sky Lab"}],
        "prop_assets": [{"prop_id": "prop_compass", "display_name": "Star Compass"}],
        "style_profiles": [{"style_id": "style_warm_comic", "display_name": "Warm Comic"}],
    }
    payload.update(overrides)
    return payload


def _scene_cast(**overrides: Any) -> dict[str, Any]:
    payload = {
        "scene_cast_id": "cast_frame_1",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "asset_bible_id": "bible_demo",
        "storyboard_plan_id": "storyboard_plan_1",
        "frame_id": "frame_0001",
        "character_ids": ["char_luna"],
        "scene_id": "scene_lab",
        "prop_ids": ["prop_compass"],
        "style_id": "style_warm_comic",
        "continuity_notes": ["Keep goggles visible"],
    }
    payload.update(overrides)
    return payload


def test_ip_design_workbench_fails_closed_without_client():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()

    render_ip_design_workbench(
        ip_design_client=None,
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert fake_ui.infos == ["ip_design.unavailable"]
    assert fake_ui.buttons == []


def test_ip_design_workbench_lists_assets_and_scene_casts():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()
    client = _FakeIPDesignClient()

    def translate(key, **kwargs):
        if key == "ip_design.asset_bible.counts":
            return (
                f"characters {kwargs['characters']} scenes {kwargs['scenes']} "
                f"props {kwargs['props']} styles {kwargs['styles']}"
            )
        if key == "ip_design.scene_cast.summary":
            return (
                f"{kwargs['scene_cast_id']} {kwargs['storyboard_plan_id']} "
                f"{kwargs['frame_id']} {kwargs['characters']} {kwargs['scene_id']} "
                f"{kwargs['props']} {kwargs['style_id']}"
            )
        return key

    render_ip_design_workbench(
        ip_design_client=client,
        ui=fake_ui,
        translate=translate,
    )

    rendered = "\n".join(fake_ui.markdowns + fake_ui.captions)
    assert "bible_demo" in rendered
    assert "IP" in rendered
    assert "cast_frame_1" in rendered
    assert "char_luna" in rendered
    assert client.calls[:3] == [
        {
            "method": "list_asset_bibles",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
        },
        {
            "method": "list_asset_bible_presets",
        },
        {
            "method": "list_scene_casts",
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "asset_bible_id": "bible_demo",
        },
    ]


def test_ip_design_workbench_renders_scene_cast_summary_from_translation_only():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()
    client = _FakeIPDesignClient()

    def translate(key, **kwargs):
        if key == "ip_design.asset_bible.counts":
            return "counts"
        if key == "ip_design.scene_cast.summary":
            return f"scene summary {kwargs['scene_cast_id']} {kwargs['frame_id']}"
        return key

    render_ip_design_workbench(
        ip_design_client=client,
        ui=fake_ui,
        translate=translate,
    )

    raw_summary = (
        "cast_frame_1 · storyboard_plan_1/frame_0001 · "
        "char_luna · scene_lab · prop_compass · style_warm_comic"
    )
    assert "scene summary cast_frame_1 frame_0001" in fake_ui.captions
    assert raw_summary not in fake_ui.captions


def test_ip_design_workbench_saves_asset_bible_through_client():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()
    fake_ui.session_state.update(
        {
            "ip_design_asset_bible_id": "bible_new",
            "ip_design_ip_profile_id": "ip_main",
            "ip_design_ip_name": "New IP",
            "ip_design_logline": "New logline",
            "ip_design_ip_type": "cartoon_animal",
            "ip_design_visual_summary": "白色卡通兔子，蓝色领结，长耳朵。",
            "ip_design_identity_lock": "白色卡通兔子, 长耳朵, 圆润脸型",
            "ip_design_color_rules": "#FFFFFF body, #006BFF tie",
            "ip_design_minimal_traits": "蓝色领结一角, 长耳朵轮廓",
            "ip_design_adaptable_slots": "服装配饰, 手持道具, 动作姿势",
            "ip_design_default_slot_preference": "prefer_supporting",
            "ip_design_presence_spectrum": "全身出镜, 半身出镜, 局部细节",
            "ip_design_role_presets": "导游讲解者：温和的讲解者\n情感陪伴者：安静的陪伴角色",
            "ip_design_identity_suppression_rules": "远景弱化耳朵内侧",
            "ip_design_semantic_boundary": "不能变成人类, 不能替代历史建筑",
            "ip_design_negative_constraints": "避免画成普通人类讲解者, 避免多余文字",
            "ip_design_visible_text_whitelist": "长乐门, 正定古城",
            "ip_design_save_asset_bible": True,
        }
    )
    client = _FakeIPDesignClient()

    render_ip_design_workbench(
        ip_design_client=client,
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    saved_call = client.calls[-1]
    assert saved_call["method"] == "save_asset_bible"
    assert saved_call["asset_bible_id"] == "bible_new"
    saved_profiles = saved_call["payload"]["ip_profiles"]
    assert len(saved_profiles) == 1
    profile = saved_profiles[0]
    assert profile["ip_profile_id"] == "ip_main"
    assert profile["name"] == "New IP"
    assert profile["logline"] == "New logline"
    assert profile["ip_type"] == "cartoon_animal"
    assert profile["visual_summary"] == "白色卡通兔子，蓝色领结，长耳朵。"
    assert profile["identity_lock"] == ["白色卡通兔子", "长耳朵", "圆润脸型"]
    assert profile["minimal_traits"] == ["蓝色领结一角", "长耳朵轮廓"]
    assert profile["adaptable_slots"] == ["服装配饰", "手持道具", "动作姿势"]
    assert profile["default_slot_preference"] == "prefer_supporting"
    assert profile["presence_spectrum"] == ["全身出镜", "半身出镜", "局部细节"]
    assert profile["role_presets"] == ["导游讲解者：温和的讲解者", "情感陪伴者：安静的陪伴角色"]
    assert profile["semantic_boundary"] == ["不能变成人类", "不能替代历史建筑"]
    assert profile["negative_constraints"] == ["避免画成普通人类讲解者", "避免多余文字"]
    assert profile["visible_text_whitelist"] == ["长乐门", "正定古城"]
    assert fake_ui.successes == ["ip_design.asset_bible.saved"]


def test_ip_design_workbench_preserves_sibling_ip_profiles_when_saving():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()
    fake_ui.session_state.update(
        {
            "ip_design_asset_bible_id": "bible_demo",
            "ip_design_ip_profile_id": "ip_main",
            "ip_design_ip_name": "Updated Main",
            "ip_design_identity_lock": "updated main rabbit",
            "ip_design_save_asset_bible": True,
        }
    )
    client = _FakeIPDesignClient(
        asset_bibles=[
            _asset_bible(
                ip_profiles=[
                    {
                        "ip_profile_id": "ip_main",
                        "name": "Main IP",
                        "identity_lock": ["main rabbit"],
                    },
                    {
                        "ip_profile_id": "ip_side",
                        "name": "Side IP",
                        "identity_lock": ["side rabbit"],
                    },
                ]
            )
        ]
    )

    render_ip_design_workbench(
        ip_design_client=client,
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    saved_profiles = client.calls[-1]["payload"]["ip_profiles"]
    assert len(saved_profiles) == 2
    main_profile = next(p for p in saved_profiles if p["ip_profile_id"] == "ip_main")
    side_profile = next(p for p in saved_profiles if p["ip_profile_id"] == "ip_side")
    assert main_profile["name"] == "Updated Main"
    assert main_profile["identity_lock"] == ["updated main rabbit"]
    assert side_profile["name"] == "Side IP"
    assert side_profile["identity_lock"] == ["side rabbit"]


def test_ip_design_workbench_reads_profile_matching_session_ip_profile_id():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()
    fake_ui.session_state.update(
        {
            "ip_design_asset_bible_select": "bible_demo",
            "ip_design_ip_profile_select": "ip_side",
        }
    )
    client = _FakeIPDesignClient(
        asset_bibles=[
            _asset_bible(
                ip_profiles=[
                    {
                        "ip_profile_id": "ip_main",
                        "name": "Main IP",
                        "logline": "Main logline",
                        "identity_lock": ["main rabbit"],
                        "visual_summary": "main visual summary",
                    },
                    {
                        "ip_profile_id": "ip_side",
                        "name": "Side IP",
                        "logline": "Side logline",
                        "identity_lock": ["side rabbit"],
                        "visual_summary": "side visual summary",
                    },
                ]
            )
        ]
    )

    render_ip_design_workbench(
        ip_design_client=client,
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    by_key = {item["key"]: item for item in fake_ui.text_inputs}
    by_area_key = {item["key"]: item for item in fake_ui.text_areas}
    assert by_key["ip_design_ip_name"]["value"] == "Side IP"
    assert by_area_key["ip_design_logline"]["value"] == "Side logline"
    assert by_key["ip_design_identity_lock"]["value"] == "side rabbit"
    assert by_area_key["ip_design_visual_summary"]["value"] == "side visual summary"


def test_ip_design_workbench_marks_ip_without_identity_anchors_unavailable():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()
    client = _FakeIPDesignClient(
        asset_bibles=[
            {
                "asset_bible_id": "bible_empty",
                "workspace_id": "workspace_1",
                "project_id": "project_1",
                "ip_profiles": [
                    {
                        "ip_profile_id": "ip_main",
                        "name": "Empty IP",
                        "identity_lock": [],
                        "identity_anchors": [],
                    }
                ],
                "character_profiles": [],
                "scene_assets": [],
                "prop_assets": [],
                "style_profiles": [],
            }
        ],
    )

    render_ip_design_workbench(
        ip_design_client=client,
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert "ip_design.asset_bible.generation_unavailable" in fake_ui.captions


def test_ip_design_workbench_saves_scene_cast_through_client():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()
    fake_ui.session_state.update(
        {
            "ip_design_scene_cast_id": "cast_new",
            "ip_design_storyboard_plan_id": "storyboard_new",
            "ip_design_frame_id": "frame_0002",
            "ip_design_character_ids": "char_luna, char_milo",
            "ip_design_scene_id": "scene_lab",
            "ip_design_prop_ids": "prop_compass",
            "ip_design_style_id": "style_warm_comic",
            "ip_design_continuity_notes": "Keep goggles visible\nKeep compass visible",
            "ip_design_save_scene_cast": True,
        }
    )
    client = _FakeIPDesignClient()

    render_ip_design_workbench(
        ip_design_client=client,
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert client.calls[-1] == {
        "method": "save_scene_cast",
        "workspace_id": "workspace_1",
        "project_id": "project_1",
        "asset_bible_id": "bible_demo",
        "scene_cast_id": "cast_new",
        "payload": {
            "storyboard_plan_id": "storyboard_new",
            "frame_id": "frame_0002",
            "character_ids": ["char_luna", "char_milo"],
            "scene_id": "scene_lab",
            "prop_ids": ["prop_compass"],
            "style_id": "style_warm_comic",
            "continuity_notes": ["Keep goggles visible", "Keep compass visible"],
        },
    }
    assert fake_ui.successes == ["ip_design.scene_cast.saved"]


def test_ip_design_workbench_imports_builtin_asset_bible_preset():
    from web.components.ip_design_workbench import render_ip_design_workbench

    fake_ui = _FakeUI()
    fake_ui.session_state.update(
        {
            "ip_design_builtin_asset_bible_preset_select": "builtin_asset_bible_demo",
            "ip_design_import_asset_bible_id": "demo_bible",
            "ip_design_import_builtin_asset_bible": True,
        }
    )
    client = _FakeIPDesignClient(
        asset_bibles=[],
        scene_casts=[],
        presets=[
            {
                "preset_id": "builtin_asset_bible_demo",
                "display_name": "Demo IP",
            }
        ],
    )

    render_ip_design_workbench(
        ip_design_client=client,
        ui=fake_ui,
        translate=lambda key, **_kwargs: key,
    )

    assert client.import_calls == [
        {
            "workspace_id": "workspace_1",
            "project_id": "project_1",
            "preset_id": "builtin_asset_bible_demo",
            "asset_bible_id": "demo_bible",
        }
    ]
    assert fake_ui.successes == ["ip_design.asset_bible.imported"]
