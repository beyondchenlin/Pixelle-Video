# dev 分支预存测试失败分析

> 分析日期：2026-05-07
> 测试环境：Python 3.12.12, pytest 9.0.2, Windows 10
> 分支：dev（基于 bf4fde5）
> 总用例：2952 passed + 71 failed = 3023

## 概览

71 个失败均为 source code 已演进但测试未同步的预存问题，与 IP Phase 2（role label 泄露修复）无关。

---

## 分类一：字段默认值/配置变更（14 个）

source code 改了默认值，测试仍断言旧值。

### test_video_api.py（4 个）

| 测试 | 根因 |
|------|------|
| `test_video_generate_request_defaults_punctuation_max_scene_count_for_punctuation_mode` | `storyboard_max_scene_count` 默认值 60→100 |
| `test_video_generate_request_defaults_deterministic_max_scene_count_for_sentence_mode` | 同上 |
| `test_video_generate_request_rejects_invalid_storyboard_contract_combinations[payload5]` | 校验规则变更，payload5 不再被拒绝 |
| `test_video_generate_request_rejects_invalid_storyboard_contract_combinations[payload6]` | 同上 |

### test_content_input_storyboard_generation.py（2 个）

| 测试 | 根因 |
|------|------|
| `test_storyboard_generation_payload_for_deterministic_modes_uses_auto_count` | `max_scene_count` 字段默认逻辑变更 |
| `test_storyboard_generation_payload_defaults_deterministic_max_scene_count` | 同上 |

### test_content_input_storyboard_ui.py（3 个）

| 测试 | 根因 |
|------|------|
| `test_punctuation_storyboard_generation_controls_show_max_scene_slider` | 滑块范围/显示条件变了 |
| `test_sentence_storyboard_generation_controls_show_max_scene_slider` | 同上 |
| `test_deterministic_storyboard_slider_uses_configured_limit_cap` | 配置上限 cap 值变更 |

### test_render_package_models.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_render_manifest_round_trip_and_timing_config_defaults` | `tts_split_mode` 默认值 `"external_only"` → `"internal_only"` |

### test_asset_bible_payload_projection.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_build_asset_bible_draft_payload_from_response_strips_response_only_fields` | `forbidden_elements` 字段未被剔除（对比断言多了该项） |

### test_storyboard_generation_service.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_deterministic_modes_use_dedicated_config_limit_when_request_omits_override` | `max_scene_count` 配置取值路径变更 |

### test_frame_processor_negative_prompt.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_compose_frame_html_forwards_layered_template_spec_to_materializer` | `layered_template_spec` 转发行为变更 |

### test_tasks_api_presentation.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_present_task_derives_video_url_from_current_request_without_mutating_result` | `video_url` 派生逻辑变更 |

---

## 分类二：生成协调器（26 个）

Coordinator 函数签名和行为变更，mock/测试未同步。

### test_generation_coordinator.py（26 个）

| 测试 | 根因 |
|------|------|
| `test_core_execute_standalone_index_tts2_workflow_releases_models_after_execute` | `_preflight()` 新增 `missing_endpoint` 参数 |
| `test_core_execute_gguf_workflow_releases_gguf_extension_after_execute` | 同上 |
| `test_core_execute_local_comfy_workflow_recovers_once_after_oom` | OOM 恢复流程变更 |
| `test_core_execute_index_tts2_oom_recovery_releases_plugin_cache_in_comfyui_mode` | 同上 |
| `test_core_execute_local_comfy_workflow_stops_when_oom_release_fails` | 同上 |
| `test_local_comfyui_workflow_session_keeps_lifecycle_open_across_batch` | session 生命周期管理变更 |
| `test_index_tts2_workflow_session_releases_models_once_at_session_exit` | model release 时序变更 |
| `test_local_comfyui_workflow_session_releases_models_for_renamed_index_tts2_file` | 同上 |
| `test_index_tts2_workflow_session_releases_models_at_session_exit` | 同上 |
| `test_index_tts2_workflow_preflights_required_extension_endpoint_before_execute` | preflight endpoint 要求变更 |
| `test_index_tts2_workflow_session_does_not_force_release_on_normal_completion` | release 策略变更 |
| `test_local_comfyui_workflow_session_can_release_at_batch_exit_inside_task_scope` | 同上 |
| `test_local_comfyui_workflow_session_fails_when_stage_release_is_not_confirmed` | 同上 |
| `test_release_comfyui_after_local_workflow_releases_models_after_batch` | release 流程变更 |
| `test_release_comfyui_after_local_workflow_logs_structured_release_result` | 日志格式变更 |
| `test_release_comfyui_after_index_tts2_workflow_logs_failed_confirmation_as_warning` | 同上 |
| `test_release_comfyui_after_index_tts2_workflow_releases_standard_and_plugin_models` | 同上 |
| `test_release_comfyui_after_index_tts2_workflow_forces_extension_cleanup_in_comfyui_mode` | extension cleanup 策略变更 |
| `test_index_tts2_release_preflight_runs_in_comfyui_cleanup_mode` | preflight 模式变更 |
| `test_force_release_comfyui_memory_uses_required_extension_endpoint` | endpoint 要求变更 |
| `test_local_comfyui_workflow_session_serializes_concurrent_workflows` | 并发序列化行为变更 |
| `test_local_comfyui_workflow_session_is_scoped_to_core_instance` | scope 管理变更 |
| `test_core_execute_gguf_connection_loss_restarts_managed_backend_and_retries` | GGUF 重连逻辑变更 |
| `test_local_comfyui_workflow_session_ignores_legacy_gguf_restart_config` | 配置键名变更 |
| `test_local_comfyui_workflow_session_releases_gguf_batch` | release 流程变更 |

---

## 分类三：IP World Controls（11 个）

`generation_world_hint` 字段交互逻辑重构。

### test_content_ip_world_controls.py（11 个）

| 测试 | 根因 |
|------|------|
| `test_render_content_ip_world_controls_keeps_world_hint_without_ip` | payload 新增 `generation_world_hint` 字段 |
| `test_render_content_ip_world_controls_returns_selected_ip_payload_without_helper_field` | payload 结构变更 |
| `test_render_content_ip_world_controls_can_use_ip_default` | 同上 |
| `test_render_content_ip_world_controls_clears_stale_ip_world_hint_when_ip_disabled` | 清除逻辑变更 |
| `test_render_content_ip_world_controls_clears_stale_ip_world_hint_when_profile_has_no_hint` | 同上 |
| `test_render_content_ip_world_controls_generates_world_hint_from_script` | 生成流程变更 |
| `test_render_content_ip_world_controls_warns_when_generating_without_script` | 警告文案变更 |
| `test_render_content_ip_world_controls_warns_and_preserves_state_when_generator_raises` | 状态保持逻辑变更 |
| `test_render_content_ip_world_controls_warns_without_rerun_for_invalid_generated_world_hint` | 校验逻辑变更 |
| `test_render_content_ip_world_controls_marks_auto_world_hint_as_manual_after_user_edit` | 标记逻辑变更 |
| `test_content_ip_world_translation_keys_exist_in_supported_locales` | i18n key 新增/删除 |

---

## 分类四：ComfyUI 后端进程管理（7 个）

Windows 平台进程模拟与实现不匹配。

### test_comfyui_backend_scripts.py（7 个）

| 测试 | 根因 |
|------|------|
| `test_stop_backend_stops_matching_listener_without_pid_file` | PID 文件不存在时的停止逻辑变更 |
| `test_stop_backend_stops_matching_listener_when_pid_file_is_invalid` | 同上 |
| `test_stop_backend_stops_matching_listener_when_pid_file_is_stale` | 同上 |
| `test_stop_backend_stops_matching_listener_when_pid_file_points_elsewhere` | 同上 |
| `test_check_backend_marks_matching_process_as_managed_without_pid_file` | 进程标记逻辑变更 |
| `test_stop_backend_stops_listener_when_pid_file_points_to_launcher` | launcher 停止策略变更 |
| `test_stop_backend_does_not_kill_unmanaged_parent_launcher` | 非托管进程保护逻辑变更 |

---

## 分类五：API 签名变更（4 个）

函数新增必填参数或校验规则，测试未更新。

### test_tasks_api_pagination.py（2 个）

| 测试 | 根因 |
|------|------|
| `test_list_tasks_page_returns_paginated_response` | `list_tasks_page()` 新增 `request` 必填参数 |
| `test_list_tasks_still_returns_plain_list` | 同上 |

### test_async_video_registry_integration.py（2 个）

| 测试 | 根因 |
|------|------|
| `test_async_video_endpoint_returns_reused_task_without_execution` | TTS 合约校验新增 voice_id 强制要求 |
| `test_async_video_endpoint_submits_new_task_without_router_execution` | 同上 |

### test_async_video_registry_integration.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_async_video_generation_fingerprint_ignores_request_id` | fingerprint 计算逻辑变更 |

---

## 分类六：工作流文件/模型缺失（5 个）

代码引用的配置/模型与实际不符。

### test_selfhost_workflows.py（4 个）

| 测试 | 根因 |
|------|------|
| `test_tts_omnivoice_api_dependency_docs_record_modelscope_priority` | ModelScope 文档缺失或过期 |
| `test_omnivoice_api_workflow_dependency_docs_exist` | 同上 |
| `test_image_z_image_turbo_gguf_defaults_to_q4_k_m_models` | 模型文件变更 |
| `test_tts_omnivoice_longform_bf16_uses_longform_node_and_safe_defaults` | workflow 节点定义变更 |
| `test_tts_omnivoice_clone_duration_bf16_uses_voice_clone_node_and_duration_param` | 同上 |

### test_z_image_downloads.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_default_download_tasks_cover_z_image_turbo_gguf_workflow_models` | 期望下载 `Q8_0.gguf` 但配置使用 `Q4_K_M.gguf` |

---

## 分类七：Pipeline 行为变更（2 个）

### test_standard_pipeline_hyperframes_mode.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_synthesize_hyperframes_audio_skips_restart_when_profile_disables_it` | 即使 profile 禁用也调度 `post-tts-batch` restart |

### test_hyperframes_compiler.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_hyperframes_compiler_uses_layer_text_style_without_global_text_rendering` | `layered_template_spec` 传递路径变更 |

### test_layered_template_preview_service.py（1 个）

| 测试 | 根因 |
|------|------|
| `test_render_preview_html_uses_text_layer_style_without_global_text_rendering` | 同上 |

---

## 总结

| 分类 | 数量 |
|------|------|
| 字段默认值/配置变更 | 14 |
| 生成协调器 | 26 |
| IP World Controls | 11 |
| ComfyUI 后端进程管理 | 7 |
| API 签名变更 | 4 |
| 工作流文件/模型缺失 | 5 |
| Pipeline 行为变更 | 3 |
| **合计** | **71** |

所有失败均为 dev 分支上的已知技术债，与本次 IP Phase 2 修复无关。修复方向统一：更新测试断言/参数以匹配当前 source code 行为。
