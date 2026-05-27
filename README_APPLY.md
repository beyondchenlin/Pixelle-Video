# Pixelle V3.1 场景绑定视觉锚点修复包

这个 zip 包包含本次 V3.1 修复涉及的完整文件，保留了项目内原始相对路径。

## 覆盖方式

在项目根目录解压覆盖：

```bash
unzip pixelle_v3_1_scene_bound_fix_files.zip -d .
```

或在 Windows 手动把 zip 里的目录覆盖到项目根目录。

## 包含内容

- `pixelle_video/services/visual_anchor_policy.py`
- `pixelle_video/models/base_visual_brief.py`
- `pixelle_video/services/base_visual_brief_planner.py`
- `pixelle_video/models/visual_anchor_planning.py`
- `pixelle_video/models/visual_anchor_integration.py`
- `pixelle_video/services/visual_anchor_placement_planner.py`
- `pixelle_video/services/visual_anchor_integration_planner.py`
- `pixelle_video/services/provider_prompt_projector.py`
- `pixelle_video/prompts/templates/visual_anchor_integration.md`
- `tests/test_visual_anchor_scene_bound_policy.py`
- `docs/visual_anchor_v3_1_scene_bound_protocol.md`

## 建议验证

```bash
uv run pytest tests/test_visual_anchor_scene_bound_policy.py
```

核心修复目标：禁止视觉锚点退化为角标、水印、logo、贴纸、悬浮图标；只允许它绑定到场景内真实物体/表面，或本帧不出现。
