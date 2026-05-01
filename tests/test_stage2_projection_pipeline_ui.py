def test_stage2_projection_preview_pipeline_is_registered_after_primary_tabs():
    from web.i18n import get_language, set_language
    from web.pipelines import get_all_pipeline_uis, get_pipeline_ui

    pipelines = get_all_pipeline_uis()

    assert [pipeline.name for pipeline in pipelines][:6] == [
        "quick_create",
        "action_transfer",
        "custom_media",
        "digital_human",
        "image_to_video",
        "stage2_prompt_plan_projection",
    ]

    pipeline = get_pipeline_ui("stage2_prompt_plan_projection")
    assert pipeline is not None
    assert pipeline.icon == "🧭"

    previous_language = get_language()
    try:
        set_language("en_US")
        assert pipeline.display_name == "Stage 2 Projection Preview"
        assert "non-persistent" in pipeline.description.lower()
        assert "generation" in pipeline.description
    finally:
        set_language(previous_language)


def test_stage2_projection_preview_pipeline_delegates_to_preview_component(monkeypatch):
    from web.pipelines import get_pipeline_ui

    pipeline = get_pipeline_ui("stage2_prompt_plan_projection")
    assert pipeline is not None

    from web.pipelines import stage2_projection

    captured = {}

    def fake_render_prompt_plan_projection_preview(*, translate=None):
        captured["translate"] = translate
        return {"projection": {"prompt_plan": {"final_prompt": "preview only"}}}

    monkeypatch.setattr(
        stage2_projection,
        "render_prompt_plan_projection_preview",
        fake_render_prompt_plan_projection_preview,
    )

    result = pipeline.render(pixelle_video=object())

    assert result == {"projection": {"prompt_plan": {"final_prompt": "preview only"}}}
    assert captured["translate"] is stage2_projection.tr
