from pixelle_video.services.prompt_trace_artifacts import write_final_prompt_artifact


def test_write_final_prompt_artifact_persists_exact_media_prompts(tmp_path):
    artifact_path = write_final_prompt_artifact(
        tmp_path,
        task_id="task_123",
        frames=[
            {
                "index": 1,
                "prompt": "a precise image prompt\nwith a second line",
                "negative_prompt": "no text, no watermark",
            }
        ],
    )

    assert artifact_path.name == "final_visual_prompts.md"
    assert artifact_path.parent.name == "prompt_traces"
    content = artifact_path.read_text(encoding="utf-8")
    assert "# Final Visual Prompts" in content
    assert "Task ID: task_123" in content
    assert "Frame count: 1" in content
    assert "```text\na precise image prompt\nwith a second line\n```" in content
    assert "```text\nno text, no watermark\n```" in content
