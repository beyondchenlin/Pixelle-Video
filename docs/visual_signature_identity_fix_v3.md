# Visual signature identity fix v3

## 问题

一次完整生成中，前两帧的视觉签名没有明显出现。日志显示：

- request 中启用的是 `series_visual_signature_enabled=True`，签名 profile 是 `dog_1`，不是 `visual_profile_id` 路线。
- 前两帧的 `visual_anchor_placement_by_frame` 其实包含“带着黑色墨镜的斑点狗”。
- 但最终 provider prompt 被 `visual_signature_clause_renderer._identity_kernel()` 降级成了“频道识别轮廓”，因为旧代码只识别兔子和麻雀，不识别动态 IP identity。

结果是：第一帧变成“频道识别轮廓浅压印纹章”，第二帧变成“频道识别轮廓装饰纹样”，图像模型没有足够信息画出斑点狗。

## 修复

1. `VisualAnchorIntegrationPlanner` 把 `identity_kernel` 写入 `VisualAnchorPlacementPlan.metadata.visual_identity_kernel`。
2. `visual_signature_clause_renderer` 优先使用 metadata 里的动态 identity kernel。
3. 缺 metadata 时，从 `image_prompt_clause` 中抽取“带着黑色墨镜的斑点狗”等短语。
4. embedded mark / surface graphic 不再写“低对比的频道识别轮廓”，改为“小面积但清晰可辨的{identity}图案”，保证可读但不抢主体。

## 验证

```powershell
uv run pytest tests/test_visual_signature_clause_renderer.py tests/test_visual_profile_pipeline_units.py
```
