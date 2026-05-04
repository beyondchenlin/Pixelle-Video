# IPProfile 结构化事实源设计

## 1. 结论

当前 IP 形象没有进入 Z-Image 文生图结果的根因，不是模型随机失效，也不是生成页世界观缺失，而是：

1. IP 设计工作台保存的是 `ip_name / logline / world_hint / style_hint / forbidden_elements` 这一组说明性字段；
2. 标准生成链路里的 `IPUsagePlanner` 和最终图片提示词主链路，真正消费的是 `identity_lock / identity_anchors / semantic_boundary / negative_constraints / color_palette / visible_text_whitelist` 这一组结构化字段；
3. 两组字段之间没有正式转换、没有统一合同、没有生成前完整性校验，导致“启用 IP”可以成功透传，但最终下发给 Z-Image 的 prompt 里没有稳定身份锚点。

本设计的目标是把 `IPProfile` 建成唯一、正式、结构化的 IP 事实源，让 IP 设计页、AssetBible API、IP 使用规划器和最终 Z-Image prompt 生成链路读取同一组字段，并在启用 IP 但身份锚点缺失时直接阻断生成。

## 2. 问题陈述

### 2.1 当前失效路径

当前标准生成链路已经支持：

- 生成页启用 IP
- 选择 AssetBible / IP Profile
- 在图片提示词主链路中按帧生成 `ip_adaptation`
- 把部分 IP 规则并入最终 Z-Image prompt

但实际生成结果仍然是“普通讲述者”，根因有两层：

1. **保存层断裂**  
   IP 设计工作台没有提供 `identity_lock / identity_anchors / semantic_boundary / negative_constraints / color_palette / visible_text_whitelist` 的正式编辑入口和保存入口。

2. **消费层严格依赖结构化字段**  
   `IPUsagePlanner` 只读取结构化字段，不读取 `style_hint / logline / forbidden_elements` 作为身份锚点来源。

于是：

- UI 里看似已经设计了“白色卡通兔子，蓝色领结”
- 但保存结果里 `identity_lock=[]`、`identity_anchors=[]`
- 生成时 `ip_enabled=true`
- 最终 prompt 里却没有“白色卡通兔子 / 蓝色领结”

### 2.2 当前问题不是世界观提示问题

`docs/superpowers/specs/2026-05-04-生成页世界观提示设计.md` 解决的是“本次文案里 IP 应该如何融入世界”，即 `generation_world_hint / generation_world_profile`。

它不解决“这个 IP 到底是谁”的源头问题。

如果 `identity_lock / identity_anchors` 为空，即使先完成生成页世界观提示，IP 也仍然缺少稳定身份事实源。因此本设计是生成页世界观提示方案的前置依赖。

## 3. 设计目标

本设计必须实现：

1. `IPProfile` 成为唯一正式的 IP 结构化事实源。
2. IP 设计工作台可以正式编辑并保存主生成链路真实消费的字段。
3. AssetBible API / schema 与 `IPProfile` 结构一一对应，不再用缩水版平铺合同表达完整 IP。
4. Z-Image 文生图主链路只消费结构化字段，不依赖 `style_hint` 猜身份锚点。
5. 当启用 IP 但身份锚点缺失时，生成直接失败并给出明确错误。
6. 本轮不做旧数据迁移，不做旧字段兼容猜测，不引入运行时 fallback。

## 4. 非目标

本设计不包含：

1. 生成页世界观提示功能本身  
   即不实现 `generation_world_hint / generation_world_profile`。
2. 参考图、LoRA、IPAdapter、图生图、角色锁图工作流。
3. 旧 AssetBible 的自动迁移脚本。
4. 从 `style_hint / forbidden_elements` 运行时推断身份锚点的兼容逻辑。
5. 多 IP Profile 的完整工作台管理体验重做。

## 5. 核心原则

### 5.1 结构化事实优先于说明性文本

以下字段只用于说明和创作辅助，不作为主生成事实源：

- `logline`
- `world_hint`
- `style_hint`

以下字段才是正式生成事实源：

- `identity_lock`
- `identity_anchors`
- `identity_suppression_rules`
- `variable_slots`
- `semantic_boundary`
- `negative_constraints`
- `color_palette`
- `visible_text_whitelist`

### 5.2 启用 IP 不等于允许空跑

如果用户显式启用了 IP，并选择了某个 `AssetBible / IPProfile`，系统就必须保证该 IP 可用于正式生成。

不能继续接受以下行为：

- `ip_enabled=true`
- `identity_lock=[]`
- `identity_anchors=[]`
- 最终静默退化成普通“讲述者”

这类情况必须在正式生成前明确失败。

### 5.3 不用兼容猜测掩盖数据源缺陷

本轮禁止：

- 从 `style_hint` 中解析“白色兔子”“蓝色领结”
- 从 `forbidden_elements` 中猜测 `negative_constraints`
- 在 prompt 组装末尾拼接一段救火文本

因为这些做法会重新制造第二套 IP 事实源。

## 6. 正式数据模型设计

### 6.1 IPProfile 的语义分层

`IPProfile` 字段分成四层：

1. **说明层**
   - `name`
   - `logline`
   - `world_hint`
   - `style_hint`

2. **身份锁定层**
   - `identity_lock`
   - `identity_anchors`
   - `identity_suppression_rules`

3. **生成约束层**
   - `semantic_boundary`
   - `negative_constraints`
   - `visible_text_whitelist`

4. **风格与变体层**
   - `variable_slots`
   - `color_palette`
   - `image_text_palette`

### 6.2 关键字段定义

#### `identity_lock`

表达这个 IP 无论如何都不能丢失的核心身份特征。  
示例：

- `白色卡通兔子`
- `长耳朵`
- `圆润脸型`

这些字段进入最终 prompt 时应保持少量、强锚点、稳定可执行。

#### `identity_anchors`

表达识别度高但允许按镜头强弱出现的辅助锚点。  
示例：

- `蓝色领结`
- `浅粉色耳朵内侧`

#### `semantic_boundary`

表达 IP 在叙事身份上的硬边界。  
示例：

- `不能替代历史建筑`
- `不能替代宗教人物`
- `不能变成人类`

#### `negative_constraints`

表达最终 Z-Image prompt 合并时需要纳入的负面画面约束。  
示例：

- `避免把角色画成普通人类讲述者`
- `避免贴纸感`
- `避免多余文字`

#### `color_palette`

内部保存色彩结构，允许同时存在：

- `hex`
- `prompt`

但只有 `prompt` 可以进入最终 Z-Image prompt。  
色号不能进入最终 prompt。

#### `visible_text_whitelist`

表达当前 IP 在图片里允许出现的中文文字白名单。  
这仍然由 Z-Image 文生图链路和文字策略共同消费。

### 6.3 `forbidden_elements` 的定位

`forbidden_elements` 不再作为正式生成链路字段。

本轮策略：

1. 不为它新增主生成消费逻辑；
2. 不把它当作 `negative_constraints` 的别名；
3. 设计工作台不再把它作为正式 IP 生成配置核心入口；
4. 若底层模型仍暂时保留该字段，也只视为历史/说明性元数据，不作为最终 prompt 事实源。

## 7. API 与持久化合同设计

### 7.1 当前问题

当前 `AssetBibleDraftRequest` 是平铺、缩水、单 IP 简化合同：

- `ip_name`
- `logline`
- `world_hint`
- `style_hint`
- `forbidden_elements`

这和 `IPProfile` 正式数据结构不一致，是根因之一。

### 7.2 推荐合同

AssetBible 的创建与保存请求都必须和正式模型形状对齐。

推荐把当前平铺合同改成嵌套结构，并让所有正式入口共用这一套合同：

- `asset_bible_id`
- `workspace_id`
- `ip_profiles`
- `character_profiles`
- `scene_assets`
- `prop_assets`
- `style_profiles`
- `metadata`

这里的“正式入口”包括：

- AssetBible API 的创建请求
- AssetBible API 的更新请求
- IP 设计工作台保存入口
- Stage2 / 草稿创建类入口

不再保留另一套仅包含 `ip_name / world_hint / style_hint` 的轻量平铺创建合同。

其中 `ip_profiles` 的元素直接对应正式 `IPProfileDraftPayload`，字段与 `IPProfile` 一一映射：

- `ip_profile_id`
- `name`
- `logline`
- `world_hint`
- `style_hint`
- `identity_lock`
- `identity_anchors`
- `identity_suppression_rules`
- `variable_slots`
- `semantic_boundary`
- `negative_constraints`
- `color_palette`
- `image_text_palette`
- `visible_text_whitelist`
- `metadata`

### 7.3 为什么不用继续扩展平铺合同

继续在 `AssetBibleDraftRequest` 顶层增加十几个字段，会带来三个问题：

1. 顶层字段和 `IPProfile` 内部字段重复表达；
2. 多 IP Profile 场景天然不兼容；
3. API schema 与持久化模型继续背离。

因此本轮推荐直接改成模型对齐的嵌套合同，而不是再给平铺请求打补丁。

## 8. IP 设计工作台设计

### 8.1 当前问题

当前 IP 设计工作台只有：

- 名称
- 一句话设定
- 世界观提示
- 视觉风格提示
- 禁止元素

没有正式入口编辑结构化身份锚点和生成约束。

### 8.2 推荐编辑区块

IP 设计工作台应至少拆成以下几个区块：

1. **基础设定**
   - IP 名称
   - 一句话设定
   - 世界观提示
   - 视觉风格提示

2. **身份锁定**
   - `identity_lock`
   - `identity_anchors`
   - `identity_suppression_rules`

3. **可变层**
   - `variable_slots`

4. **语义边界与负约束**
   - `semantic_boundary`
   - `negative_constraints`

5. **颜色与文字规则**
   - `color_palette`
   - `visible_text_whitelist`

### 8.3 当前阶段的 UI 完整性要求

本轮不要求重做整个 IP 设计页布局，但必须做到：

1. 正式可编辑正式字段；
2. 保存后返回值与加载值一致；
3. 用户能从界面上看出这个 IP 是否满足“可用于正式生成”的最低条件。

除 IP 设计工作台外，任何创建 AssetBible 的正式入口也必须直接提交 `ip_profiles` 嵌套结构，不能继续单独发送平铺 IP 字段。

### 8.4 生成可用性状态

工作台应显示一个最小可用性状态：

- `可用于生成`
- `缺少身份锚点，暂不可用于生成`

这不是阻断保存，而是阻断正式使用。

## 9. 生成链路中的完整性校验

### 9.1 校验位置

完整性校验应该放在标准生成主链路正式进入 IP 规划前，而不是放在前端本地猜测。

推荐在解析完：

- `ip_enabled`
- `ip_asset_bible_id`
- `ip_profile_id`
- 已加载 `AssetBible / IPProfile`

之后，进入 `IPUsagePlanner.plan_batch(...)` 之前执行。

### 9.2 阻断条件

当满足以下条件时，必须直接失败：

1. `ip_enabled=true`
2. 已选择 `AssetBible / IPProfile`
3. `identity_lock` 与 `identity_anchors` 合并后为空

### 9.3 错误语义

错误信息必须直接指向可操作原因，例如：

`当前 IP 形象缺少身份锚点，无法接入正式 Z-Image 生成。请先在 IP 设计工作台补全 identity_lock 或 identity_anchors。`

禁止继续静默降级为普通“讲述者”。

## 10. 最终 Z-Image Prompt 规则

### 10.1 正式来源

最终 Z-Image prompt 中与 IP 身份相关的自然语言，只能来自：

- `identity_lock`
- `identity_anchors`
- `color_palette[*].prompt`
- `semantic_boundary`
- `negative_constraints`
- `visible_text_whitelist`

### 10.2 非正式来源

以下字段不能作为硬身份事实源直接参与 prompt 生成：

- `logline`
- `style_hint`
- `forbidden_elements`

它们可以保留给创作辅助或编辑理解，但不能承担“源头修复”的职责。

### 10.3 验收标准

当启用 IP 且 `presence_type` 允许可见时，最终 prompt 必须能看到对应身份锚点。  
例如对“正定向导兔”这一类 IP，最终 prompt 不应只有“讲述者”，而应包含类似：

- `白色卡通兔子`
- `长耳朵`
- `蓝色领结`

至少一部分强识别锚点。

## 11. 与生成页世界观提示方案的关系

### 11.1 先后关系

本设计是 `2026-05-04-生成页世界观提示设计.md` 的前置依赖。

正确顺序应为：

1. 修复 `IPProfile` 结构化事实源；
2. 确保启用 IP 后能稳定生成身份锚点；
3. 再让 `generation_world_hint / generation_world_profile` 去决定“这次内容里如何融入”。

### 11.2 边界划分

`IPProfile` 回答：

- 这个 IP 是谁
- 哪些身份锚点不能丢
- 哪些语义边界不能破

`generation_world_profile` 回答：

- 这次文案的世界是什么
- 这次内容里 IP 应以什么方式融入

两者不能互相替代。

## 12. 测试策略

本设计要求至少补以下测试层：

1. **模型层**
   - `IPProfile` 结构化字段序列化/反序列化
   - 无效色号 prompt 拒绝
   - 空/重复锚点校验

2. **API 层**
   - AssetBible 保存请求可完整收发结构化 `ip_profiles`
   - 加载后字段不丢失

3. **UI 层**
   - IP 设计工作台能回填、编辑、保存结构化字段
   - 可用性状态显示正确

4. **生成链路层**
   - 启用 IP 且锚点为空时直接失败
   - 启用 IP 且锚点完整时最终 prompt 包含身份锚点
   - 未启用 IP 的旧标准生成不受影响

## 13. 实施顺序建议

推荐按以下顺序实施：

1. 先改 AssetBible / IPProfile API 合同，使其与正式模型对齐；
2. 再统一所有正式创建/保存入口（IP 设计工作台、Stage2 草稿创建等）到 `ip_profiles` 嵌套合同；
3. 再加生成前完整性校验；
4. 最后补最终 prompt 层验收测试。

不要先做生成页世界观提示，也不要先做运行时 fallback。

## 14. 最终建议

采用以下正式策略：

1. 以 `IPProfile` 为唯一正式 IP 事实源；
2. 废除“说明文本承担正式身份事实”的隐式做法；
3. 用嵌套、模型对齐的 AssetBible 创建与保存合同替换当前缩水平铺合同；
4. 统一所有正式创建/保存入口到这套嵌套合同，不再保留平铺轻量创建分支；
5. 在 IP 设计工作台正式暴露结构化身份与约束字段；
6. 启用 IP 且身份锚点为空时直接阻断生成；
7. 不做旧数据迁移，不做旧字段兼容猜测，不做运行时补丁；
8. 在此基础上，再推进生成页世界观提示方案。
