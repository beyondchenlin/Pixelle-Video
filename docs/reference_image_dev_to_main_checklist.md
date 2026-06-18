# 参考图链路 dev -> main/release 验收说明

## 当前策略

参考图能力已经接入上传、资产化、Vision 分析上下文、prompt-only 注入和 selfhost workflow 物理注入边界，但上线策略仍应保持灰度：

- 公共 API 上传入口默认关闭。
- Web UI 不默认展示参考图上传控件。
- 先验证 `workflow_injection_mode=off` 的旧路径安全，再验证 `auto` 和 `required`。
- 物理注入只允许已声明 reference image 参数或显式配置白名单的 selfhost workflow。

## 合并前必跑

```bash
python -m py_compile \
  api/reference_image_upload_store.py \
  api/routers/reference_images.py \
  api/schemas/reference_image.py \
  api/schemas/video.py \
  api/routers/video.py \
  api/app.py \
  pixelle_video/services/media.py

PYTHONPATH=. python -m pytest -q \
  tests/api/test_reference_image_upload_store.py \
  tests/api/test_video_reference_image_boundary.py \
  tests/services/test_reference_image_asset_service.py \
  tests/services/test_reference_image_workflow_binding.py \
  tests/services/test_media_reference_image_workflow_binding.py
```

GitHub Actions 中的 `Reference Image CI` 也应在目标分支通过。

## 灰度环境变量

```bash
PIXELLE_REFERENCE_IMAGE_API_ENABLED=true
PIXELLE_REFERENCE_IMAGE_UPLOAD_BASE_PATH=_runtime/reference_image_uploads
PIXELLE_REFERENCE_IMAGE_MAX_UPLOAD_SIZE_MB=20
PIXELLE_REFERENCE_IMAGE_MAX_EDGE_PX=8192
PIXELLE_REFERENCE_IMAGE_MAX_PIXELS=40000000
PIXELLE_REFERENCE_IMAGE_UPLOAD_TTL_SECONDS=604800
```

`PIXELLE_REFERENCE_IMAGE_UPLOAD_TTL_SECONDS=0` 可临时禁用 upload store TTL，但 release 环境不建议长期禁用。

## 灰度验证顺序

1. 上传参考图，确认返回 `upload_id` 和 `artifact_id`。
2. 使用 `workflow_injection_mode=off` 生成，确认上传、资产化、Vision 分析、prompt-only 上下文和 planning snapshot 正常。
3. 使用 `workflow_injection_mode=auto` 生成，确认支持 reference image 的 selfhost workflow 会注入，不支持时跳过。
4. 使用 `workflow_injection_mode=required` 生成，确认不支持 reference image 的 workflow 会 fail-fast。

## 产物检查

每次灰度生成后检查：

```text
reference_image/asset.json
reference_image/analysis.json
reference_image/visual_context.json
prompt_traces/**/final_visual_prompts.md
prompt_traces/**/media_result.md
```

确认 public trace 和结果摘要只包含：

```text
sha256
mime_type
width
height
byte_size
upload_id/artifact_id
workflow_asset_relative_path
```

不得出现：

```text
用户上传文件名之外的本地绝对路径
upload-store 绝对路径
base64 图片内容
```

## Workflow 白名单

`config.example.yaml` 中提供了 `reference_image.workflow_param_overrides` 示例。合并前不要在真实配置中使用全局 `*`，除非所有 selfhost workflow 都已验证能安全消费同名参数。

建议先按单个 workflow key 配置：

```yaml
reference_image:
  workflow_injection_mode: off
  workflow_param_overrides:
    "selfhost/image_reference.json": "reference_image"
```

灰度验证通过后，再把请求级 `workflow_injection_mode` 从 `off` 切到 `auto` 或 `required`。

## 安全回归

手动确认以下输入会被拒绝：

```json
{ "ref_image": "/etc/passwd" }
```

```json
{ "reference_image": { "path": "/etc/passwd" } }
```

```json
{ "reference_image": { "upload_id": "../secret" } }
```

还应验证以下上传坏输入：

```text
BMP 文件改名 reference.png
超大像素 PNG
空文件
非图片文件
```

## 回滚点

如灰度过程中出现异常，优先回滚到 prompt-only：

```json
{
  "reference_image": {
    "workflow_injection_mode": "off"
  }
}
```

如上传入口本身出现异常，关闭：

```bash
PIXELLE_REFERENCE_IMAGE_API_ENABLED=false
```

如 upload store 清理策略影响排查，可临时设置：

```bash
PIXELLE_REFERENCE_IMAGE_UPLOAD_TTL_SECONDS=0
```

排查完成后应恢复 TTL。
