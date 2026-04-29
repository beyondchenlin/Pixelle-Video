# 22 Quality Evaluation / Admin 分方案

用途：定义质量评估、运营观测、管理后台和商业化增强能力。  
上级文档：`MASTER_PIXELLE_AI_DRAMA_COMIC_PLATFORM_PLAN.md`

---

## 1. 定位

质量评估和管理后台是平台成熟后的增强能力，不应阻塞第一阶段分镜图工作台。

阶段 1 必须做结构校验，但不做复杂主观质量评分。

---

## 2. 结构校验

第一阶段必须有的校验：

```text
frame_id 必须稳定且唯一
ArtifactVersion 必须属于对应 Artifact
selected_image_version_id 必须属于当前 frame
PromptPlan 必须能追溯到 StoryboardPanel
Trace event 必须包含 job_id / stage / status
SceneCast 引用 ID 必须存在
```

这些是工程正确性，不是质量评分，不能后置。

---

## 3. 质量评估

后续可加入：

```text
prompt completeness score
image quality score
character consistency score
style consistency score
video motion score
audio alignment score
```

评分来源可以是规则、VLM、人工审核或混合策略。

---

## 4. 管理后台

Admin 需要查看：

- 项目。
- 用户。
- 工作区。
- 任务。
- Worker。
- Provider。
- UsageLedger。
- 失败率。
- 成本。
- 存储。

---

## 5. 运营指标

```text
generation_success_rate
average_generation_latency
provider_failure_rate
cost_per_project
regeneration_rate
selected_candidate_rank
storage_growth
public_api_usage
```

这些指标依赖 Artifact、Trace、Provider 和 Billing 数据稳定后再建设。

---

## 6. 审计

需要支持：

- 谁创建了项目。
- 谁发起了生成。
- 谁选择了某个版本。
- 谁触发了重抽。
- 哪个 Provider 生成了结果。
- 哪次扣费对应哪个 ArtifactVersion。

---

## 7. 阶段边界

阶段 10 做完整 Quality / Admin。

早期只做：

- 结构校验。
- Trace 基础字段。
- 失败原因可读。
- 简单统计日志。

---

## 8. 验收标准

- 结构校验能阻止明显坏数据进入工作台。
- 管理后台能定位失败任务。
- Provider 成本和成功率可统计。
- 质量评分不影响基础生成链路。
- 审计记录能追溯到用户、任务和 ArtifactVersion。

---

## 9. 非目标

- 不在阶段 1 做复杂 VLM 评分。
- 不在阶段 1 做完整运营后台。
- 不在阶段 1 用质量评分决定是否自动覆盖用户选择。
