# Pixelle-Video 全量规划文档索引

这套文档用于把当前讨论沉淀成可交给 Codex / 本地开发助手继续实现的工程规划。

## 文档列表

0. `MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`  
   总控方案，定义 Pixelle AI 短剧漫剧平台的总体目标、全部分方案、阶段路线、依赖关系和开发准入规则。后续开发应先读此文档，再进入具体分方案或阶段实施计划。

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

14. `12A_TEXT_IMAGE_PROMPT_STAGE1A_SUBPLAN.md`
    Stage 1A 文案与图片提示词正式分方案，约束主题/文案、ScriptDraft、StoryboardPlan、图片提示词和 PromptPlan。

15. `13_STORYBOARD_WORKBENCH_SUBPLAN.md`
    分镜图工作台正式分方案，约束 StoryboardPanel、候选图、选择、重抽、锁定和 stale 状态。

16. `14_ARTIFACT_TRACE_REGENERATION_SUBPLAN.md`
    Artifact、ArtifactVersion、GenerationTrace 和局部重跑正式分方案。

17. `15_ASSETBIBLE_SCENECAST_PROMPTCOMPOSER_SUBPLAN.md`
    AssetBible、SceneCast、PromptPlan、PromptComposer 和 PromptProjection 正式分方案。

18. `16_WORKFLOW_SKELETON_SUBPLAN.md`
    最小 Workflow Skeleton 正式分方案，约束 NodeContractLite、WorkflowRunLite 和系统预设流程。

19. `17_WORKER_QUEUE_DISTRIBUTED_SUBPLAN.md`
    Worker、Queue、多机器执行、lease、heartbeat 和任务恢复正式分方案。

20. `18_PROVIDER_RESOURCE_RESOLVER_SUBPLAN.md`
    Provider、ProviderCapability、ResourceResolver 和强控制资源 ID 正式分方案。

21. `19_FLOWGRAM_ADAPTER_SUBPLAN.md`
    FlowGram Adapter 正式分方案，明确 FlowGram 是 Studio 外壳，不是 Pixelle Core 事实源。

22. `20_SAAS_BILLING_PUBLIC_API_SUBPLAN.md`
    SaaS、权限、计费、UsageLedger 和 Public API 正式分方案。

23. `21_VIDEO_EXTENSION_SUBPLAN.md`
    视频扩展正式分方案，覆盖 first frame、last frame、motion prompt、video segment 和 final render artifact。

24. `22_QUALITY_EVALUATION_ADMIN_SUBPLAN.md`
    Quality Evaluation、Admin、运营观测和审计正式分方案。

## 推荐阅读顺序

如果是让 Codex 直接辅助开发，建议按这个顺序：

```text
MASTER -> 
01 -> 02 -> 03 -> 04 -> 12A -> 13 -> 14 -> 15 -> 12
```

如果是先做文案和图片提示词生成，建议按这个顺序：

```text
MASTER ->
02 -> 04 -> 12A -> 15
```

如果是先做商业化后端规划，建议按这个顺序：

```text
MASTER ->
01 -> 06 -> 07 -> 08 -> 10 -> 11 -> 17 -> 18 -> 20
```

如果是先做产品体验和重抽卡：

```text
MASTER ->
02 -> 03 -> 04 -> 12A -> 13 -> 14 -> 15
```

如果是理解完整平台化路线，建议按这个顺序：

```text
MASTER ->
12A -> 13 -> 14 -> 15 -> 16 -> 17 -> 18 -> 19 -> 20 -> 21 -> 22
```

## 当前总目标

Pixelle-Video 不应只定位为本地一键生成工具，而应逐步演进为：

```text
Pixelle Core        视频生成核心引擎
Pixelle Studio      面向用户的 Web 创作工作台
Pixelle API         面向第三方/商业用户的强控制 API
Pixelle Workers     多机器、多 Provider 的分布式生成系统
```
