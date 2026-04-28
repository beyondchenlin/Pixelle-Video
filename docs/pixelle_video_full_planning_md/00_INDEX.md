# Pixelle-Video 全量规划文档索引

这套文档用于把当前讨论沉淀成可交给 Codex / 本地开发助手继续实现的工程规划。

## 文档列表

1. `01_PROJECT_TARGET_AND_SYSTEM_BOUNDARY.md`  
   项目目标、当前定位、未来 SaaS/API 平台边界。

2. `02_TEXT_GENERATION_PIPELINE_REDESIGN.md`  
   用户输入主题、大模型生成文案、旁白、图片提示词的完整链路重构。

3. `03_IP_LIBRARY_AND_VISUAL_CONSISTENCY.md`  
   IP 库、角色库、道具库、世界观库、风格预设的设计。

4. `04_PROMPT_COMPOSER_AND_SCENE_CASTING.md`  
   Prompt Composer、Scene Casting、多角色分配、统一画风和角色一致性。

5. `05_GENERATION_TRACE_AND_LOGGING.md`  
   生成过程可视化、LLM 对话日志、任务事件流、Debug Trace。

6. `06_API_FIRST_SAAS_ARCHITECTURE.md`  
   FastAPI 分层、内部 API、对外 API、强控制参数体系。

7. `07_AUTH_PERMISSION_BILLING_AND_RESOURCE_POLICY.md`  
   用户、会员、权限、额度、资源白名单、计费策略。

8. `08_DISTRIBUTED_DEPLOYMENT_AND_WORKERS.md`  
   多机器部署、Docker Compose、Worker 队列、M4 与 Windows GPU 机器分工。

9. `09_ARTIFACT_VERSIONING_AND_REGENERATION.md`  
   文案、旁白、图片提示词、图片、音频、帧视频、最终视频的版本化与二次生成。

10. `10_PROVIDER_ABSTRACTION_LOCAL_AND_CLOUD.md`  
    本地模型、在线模型、ComfyUI、RunningHub、云图像/TTS Provider 抽象。

11. `11_DATABASE_QUEUE_STORAGE_SCHEMA.md`  
    数据库、任务队列、对象存储、项目产物目录结构建议。

12. `12_MVP_IMPLEMENTATION_PLAN_FOR_CODEX.md`  
    第一阶段 MVP 开发顺序，按文件、模块、接口拆任务。

13. `ALL_IN_ONE_PIXELLE_VIDEO_FULL_PLAN.md`  
    合并版完整文档。

## 推荐阅读顺序

如果是让 Codex 直接辅助开发，建议按这个顺序：

```text
01 -> 02 -> 03 -> 04 -> 05 -> 06 -> 08 -> 09 -> 12
```

如果是先做商业化后端规划，建议按这个顺序：

```text
01 -> 06 -> 07 -> 08 -> 10 -> 11
```

如果是先做产品体验和重抽卡：

```text
02 -> 03 -> 04 -> 05 -> 09
```

## 当前总目标

Pixelle-Video 不应只定位为本地一键生成工具，而应逐步演进为：

```text
Pixelle Core        视频生成核心引擎
Pixelle Studio      面向用户的 Web 创作工作台
Pixelle API         面向第三方/商业用户的强控制 API
Pixelle Workers     多机器、多 Provider 的分布式生成系统
```
