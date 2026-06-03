"""
手动测试 IP 管线：观察 ip_scene_description 是否正确注入 LLM prompt。
运行方式：uv run python tests/manual_test_ip_pipeline.py
"""

# ruff: noqa: E402

import asyncio
import hashlib
import logging

logging.disable(logging.CRITICAL)

from pixelle_video.models.asset_bible import IPProfile
from pixelle_video.models.prompt_context import PromptContextEnvelope
from pixelle_video.models.storyboard_plan import StoryboardPlan, StoryboardPlanFrame
from pixelle_video.services.ip_usage_planner import IPFrameAppearancePlanner
from pixelle_video.utils.content_generators import _enrich_prompt_contexts_with_ip


def make_ip_profile() -> IPProfile:
    return IPProfile(
        series_visual_signature_profile_id="demo",
        workspace_id="ws1",
        project_id="proj1",
        name="白兔导游",
        identity_lock=("白色卡通兔子", "长耳朵", "蓝色领带"),
        identity_anchors=("圆脸", "红色腮红"),
        color_palette={
            "body": {"hex": "#FFFFFF", "prompt": "纯白色身体"},
            "tie": {"hex": "#006BFF", "prompt": "鲜明宝蓝色领带"},
        },
        adaptable_slots=("服装", "道具", "动作姿势"),
    )


async def main():
    ip_profile = make_ip_profile()

    frames = [
        StoryboardPlanFrame(
            index=1,
            source_text="白兔导游站在古城门前介绍正定历史",
            visual_goal="展现古城门与导游",
            prompt_intent="建立空间",
            frame_id="frame_0001",
            shot_type="中景",
            shot_purpose="叙事",
            primary_subject="白兔导游",
        ),
        StoryboardPlanFrame(
            index=2,
            source_text="古城建筑群远景",
            visual_goal="展示古城全貌",
            prompt_intent="空间切换",
            frame_id="frame_0002",
            shot_type="远景",
            shot_purpose="空镜过渡",
            primary_subject="古城建筑",
        ),
        StoryboardPlanFrame(
            index=3,
            source_text="导游指着城墙讲述历史",
            visual_goal="互动讲解场景",
            prompt_intent="叙事展开",
            frame_id="frame_0003",
            shot_type="中近景",
            shot_purpose="互动",
            primary_subject="城墙",
        ),
    ]

    source_text = " ".join(f.source_text for f in frames)
    digest = hashlib.sha256(source_text.strip().encode("utf-8")).hexdigest()

    plan = StoryboardPlan(
        plan_id="manual_test",
        revision=1,
        mode="smart",
        count_mode="auto",
        requested_scene_count=None,
        resolved_scene_count=len(frames),
        source_text=source_text,
        source_digest=digest,
        frames=tuple(frames),
    )

    print("=" * 60)
    print("第 1 步：IPFrameAppearancePlanner（规则回退）")
    print("=" * 60)
    planner = IPFrameAppearancePlanner()
    packages = await planner.plan_batch(
        storyboard_plan=plan,
        ip_profile=ip_profile,
        resolved_style=None,
        scene_casts_by_frame=None,
        generation_world_profile=None,
    )

    for pkg in packages:
        print(f"  帧 {pkg.frame_id}:")
        print(f"    presence_type:      {pkg.ip_presence_type.value}")
        print(f"    prompt_weight:      {pkg.prompt_weight}")
        print(f"    role_slot:          {pkg.role_slot.value if pkg.role_slot else 'N/A'}")
        print(f"    appearance_description: {pkg.appearance_description}")
        print(f"    negative_constraints: {list(pkg.negative_constraints)[:2]}")
        print()

    print("=" * 60)
    print("第 2 步：_enrich_prompt_contexts_with_ip() 注入到 frame_context")
    print("=" * 60)
    prompt_contexts = PromptContextEnvelope(
        plan_context={"plan_source_text": source_text},
        frame_contexts=[
            {
                "frame_source_text": f.source_text,
                "visual_goal": f.visual_goal,
                "prompt_intent": f.prompt_intent,
            }
            for f in frames
        ],
    )

    enriched = _enrich_prompt_contexts_with_ip(
        prompt_contexts,
        expected_count=len(frames),
        packages=packages,
        style_context={"style_kind": "visual_only"},
    )

    for i, ctx in enumerate(enriched.frame_contexts):
        print(f"  帧 {i}:")
        desc = ctx.get("ip_scene_description", "")
        if desc:
            print(f"    ✅ ip_scene_description: {desc}")
        else:
            print("    ❌ ip_scene_description: (空！)")
        nc = ctx.get("ip_negative_constraints", [])
        if nc:
            print(f"    ✅ ip_negative_constraints: {len(nc)} 条")
        itp = ctx.get("ip_image_text_plan", {})
        if itp:
            print(f"    ✅ ip_image_text_plan: {itp.get('summary_text', '')!r}")
        print()

    print("=" * 60)
    print("第 3 步：验证全链路")
    print("=" * 60)
    checks_ok = True
    for i, ctx in enumerate(enriched.frame_contexts):
        if not ctx.get("ip_scene_description"):
            print(f"  ❌ 帧 {i}: ip_scene_description 为空")
            checks_ok = False
        if not isinstance(ctx.get("ip_negative_constraints"), list):
            print(f"  ❌ 帧 {i}: ip_negative_constraints 不是 list")
            checks_ok = False

    if checks_ok:
        print("  ✅ 所有检查通过！IP 数据已正确注入 frame_context。")
        print()
        print("现在可以在 Streamlit 中验证最终图片效果：")
        print("  uv run streamlit run web/app.py")
        print("  → 选择爱情文案 + 白兔导游 IP + 高级分镜")
        print("  → 检查生成的 prompt 日志是否包含 ip_scene_description")
        print("  → 检查最终图片中 IP 兔子是否自然融入场景")
    else:
        print("  ❌ 有空字段！")


if __name__ == "__main__":
    asyncio.run(main())
