from web.pipelines import get_all_pipeline_uis


def test_home_pipeline_tabs_keep_quick_create_first():
    pipelines = get_all_pipeline_uis()

    assert [pipeline.name for pipeline in pipelines][:5] == [
        "quick_create",
        "action_transfer",
        "custom_media",
        "digital_human",
        "image_to_video",
    ]
