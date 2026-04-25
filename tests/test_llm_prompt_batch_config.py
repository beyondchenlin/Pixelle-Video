from pixelle_video.config import config_manager
from pixelle_video.config.schema import PixelleVideoConfig


def test_config_manager_exposes_and_updates_llm_prompt_batch_settings():
    original_config = config_manager.config
    try:
        config_manager.config = PixelleVideoConfig()

        llm_config = config_manager.get_llm_config()
        assert llm_config["prompt_batch_size"] == 10
        assert llm_config["prompt_batch_concurrent_limit"] == 1

        config_manager.set_llm_config(
            api_key="key",
            base_url="https://example.test/v1",
            model="demo-model",
            prompt_batch_size=6,
            prompt_batch_concurrent_limit=3,
        )

        updated = config_manager.get_llm_config()
        assert updated["api_key"] == "key"
        assert updated["base_url"] == "https://example.test/v1"
        assert updated["model"] == "demo-model"
        assert updated["prompt_batch_size"] == 6
        assert updated["prompt_batch_concurrent_limit"] == 3
    finally:
        config_manager.config = original_config

