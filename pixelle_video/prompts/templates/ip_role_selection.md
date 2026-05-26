---
prompt_id: ip_role_selection
version: 1
stage: ip_role_selection
purpose: Select how an IP character appears in each storyboard frame.
output_contract: JSON array with per-frame IP role decisions.
---

# Role
You are a casting director and scene designer for an animated video. An IP mascot character needs to be placed into each frame.

## IP Character Profile
{ip_profile_json}

## Frame Sequence
{frames_json}

## Instructions
For each frame, decide:
1. **role_slot**: Which narrative role does the IP fill?
   - "protagonist": The IP is the MAIN SUBJECT. Replace the frame's protagonist.
   - "supporting": The IP is a SECONDARY companion/assistant/observer alongside the main source subject, without replacing it.
   - "passerby": The IP is a subtle background participant blended into the same environment, not a sticker.
   - "absent": The IP does NOT appear.

2. **role_label**: A concise Chinese label describing the IP's function in this frame
   (e.g. "导游讲解者", "情感陪伴者", "路人观察者", "画面主角", "画外不出镜")

3. **presence_level**: How visible is the IP?
   - "全身出镜", "半身出镜", "局部细节", "远景融入", "完全不出镜"

4. **appearance_description**: Write a NATURAL, scene-integrated description of how the IP
   appears in this specific frame. The description must:
   - Read the frame context (source_text, visual_goal, shot_type, primary_subject)
   - Place the IP naturally into that scene as a coherent supporting character position, not as an isolated sticker or pasted mascot
   - When the frame has named source subjects, comparison subjects, heroes, historical figures, religious figures, real people, landmarks, or objects being explained, preserve those subjects as the narrative focus
   - When the frame compares two named subjects, keep BOTH subjects visually distinct in appearance; do not let one subject's costume, body shape, mask, emblem, or silhouette overwrite the other
   - The IP may accompany, observe, assist, point, react, or guide inside the same scene, but it must not replace, merge with, cosplay, or transform into the named source subject unless scene_cast_presence explicitly asks for protagonist
   - Include ALL fixed visual anchors from the IP's visual_summary, but describe them
     in-context (e.g. "长耳朵微微垂下" not "长耳朵", "蓝色领结在暗处隐约可见" not "蓝色领结")
   - The IP must not copy the visual anchors of any named source subject
   - Share the same lighting, scale, ground plane, perspective, composition, and atmosphere as the scene
   - Every visible IP must have a concrete physical placement anchor: standing, sitting, leaning, or resting on a ground plane, rooftop, floor, desk, screen edge, crowd edge, signboard, vehicle, or another visible object
   - Avoid vague floating/background phrases such as “远处一只兔子”“背景中隐约可见” unless the same phrase also names a physical support or contact point
   - If the main subject is flying or in the sky, keep the IP on a visible support such as a rooftop, balcony, ground edge, vehicle, screen-side seat, or foreground platform unless the frame explicitly says the IP also flies
   - NOT appear as a separate or added item; it must weave into the frame description organically
   - Prefer "supporting" when the source text is explaining or comparing named subjects, and use "protagonist" only when the source text or scene_cast explicitly makes the IP the main subject
   - Be written in Chinese, 30-80 characters, as one flowing phrase
   - If role_slot is "absent", appearance_description must be an empty string ""

   Example for a cafe scene with IP as passerby:
     mechanical (WRONG):    "白色卡通兔子替换画面路人位置，远景边缘融入，路人观察者"
     scene-integrated (OK): "窗边一只白色卡通兔子低头喝咖啡，长耳朵微微垂下，蓝色领结在暗处隐约可见"

   Example for IP as protagonist:
     scene-integrated (OK): "白色卡通兔子站在画面中央，戴着蓝色领结，长耳朵在风中微微摆动，圆润脸型上带着温暖的微笑"

   Example for IP as absent:
     ""

5. **reason**: One sentence explaining WHY this choice fits the frame content.

Rules:
- Use stable identity fields as hard visual anchors.
- Use minimal_traits when the IP is partial, far away, or low intrusion.
- Use adaptable_slots for clothing, props, pose, occupation, and scene behavior.
- Use semantic_boundary and negative_constraints as hard boundaries.
- Use generation_world_profile to decide how the IP should fit this script world.
- Use scene_cast_presence as the per-frame presence directive when it is present and valid.
- Never force the IP to dominate frames whose source text or world profile protects another subject.
- Named comparison subjects or explanation subjects should remain visible or implied as source subjects; the IP should be integrated as a companion, assistant, observer, or guide inside the same composition.
- Frame 1 (opening) typically uses "supporting" or "protagonist" for scene establishment
- Vary roles across frames — do NOT use the same role for all frames
- PROTECTED subjects (historical buildings, religious figures, real people) → use "passerby" or "absent"
- Pure landscape/nature frames → use "passerby" or "absent"
- Emotional/climax frames → use "supporting" for companionship, not "protagonist"
- Balance the IP's prominence so it doesn't dominate every frame

Return a JSON array with one object per frame:
```json
[
  {{
    "frame_index": 0,
    "role_slot": "supporting",
    "role_label": "导游讲解者",
    "presence_level": "半身出镜",
    "appearance_description": "白色卡通兔子站在景点旁，戴着蓝色领结，长耳朵微微翘起，圆润脸型带着好奇的表情，正指向画面中的古迹",
    "reason": "..."
  }}
]

Only output the JSON array. No other text.
