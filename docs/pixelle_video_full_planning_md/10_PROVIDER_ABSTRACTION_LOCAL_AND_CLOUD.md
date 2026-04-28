# 10 Provider 抽象：本地与云端混合

## 1. 背景

当前文本类多使用在线大模型，图片/TTS/合成偏本地。未来可能出现：

```text
本地 Z-Image
ComfyUI
RunningHub
云图像 API
云 TTS API
本地 TTS
云视频模型
```

所以需要 Provider 抽象。

## 2. Provider 总体类型

```text
TextProvider
ImageProvider
TTSProvider
VideoProvider
BGMProvider
RenderProvider
StorageProvider
```

## 3. ImageProvider

```python
class ImageGenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    width: int
    height: int
    seed: int | None = None
    workflow_id: str | None = None
    style_id: str | None = None
    metadata: dict = {}

class ImageGenerateResult(BaseModel):
    artifact_id: str
    object_key: str
    url: str
    seed: int | None = None
    provider: str
    metadata: dict = {}
```

接口：

```python
class ImageProvider(Protocol):
    provider_id: str

    async def generate(self, request: ImageGenerateRequest) -> ImageGenerateResult:
        ...
```

实现：

```text
LocalComfyUIImageProvider
ZImageLocalProvider
RunningHubImageProvider
CloudImageAPIProvider
```

## 4. TTSProvider

```python
class TTSRequest(BaseModel):
    text: str
    voice_id: str
    speed: float | None = None
    emotion: str | None = None
    metadata: dict = {}

class TTSResult(BaseModel):
    artifact_id: str
    object_key: str
    url: str
    duration: float
    provider: str
```

实现：

```text
EdgeTTSProvider
LocalTTSProvider
ComfyUITTSProvider
CloudTTSProvider
```

## 5. Provider 选择策略

新增：

```text
ProviderRouter
```

职责：

```python
select_image_provider(user, request, job_context)
select_tts_provider(user, request, job_context)
fallback_provider_on_failure()
```

选择依据：

```text
用户套餐
当前队列长度
GPU 是否忙
任务优先级
成本
质量要求
是否允许云端
```

## 6. 示例策略

```text
Free 用户：
  image.fast -> Windows 16G 本地低优先级

Pro 用户：
  image.high -> Windows 24G 本地高优先级

Enterprise：
  cloud image provider 或专用队列

GPU 忙：
  如果用户套餐允许，则 fallback 到 cloud provider
```

## 7. Provider Registry

```python
class ProviderInfo(BaseModel):
    provider_id: str
    provider_type: Literal["text", "image", "tts", "video"]
    display_name: str
    enabled: bool
    local: bool
    required_plan: str | None = None
    cost_multiplier: float = 1.0
    capabilities: dict = {}
```

## 8. API

管理员：

```http
GET /api/v1/admin/providers
PATCH /api/v1/admin/providers/{provider_id}
```

内部：

```http
GET /api/v1/internal/providers/available
```

用户资源：

```http
GET /api/v1/app/resources/providers
```

返回时根据用户权限过滤。

## 9. 本地 ComfyUI 节点

每个 GPU 节点可以暴露：

```text
COMFYUI_URL=http://win-gpu-24g:8188
PROVIDER_ID=local_zimage_24g
```

Worker 从队列取 image 任务后，调用本地 ComfyUI，再上传结果到对象存储。

## 10. 未来扩展

以后接云端时，不改 pipeline，只新增 provider：

```text
CloudImageAPIProvider
```

然后在 provider router 里选择即可。
