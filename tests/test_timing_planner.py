from pixelle_video.models.storyboard import StoryboardFrame
from pixelle_video.services.timing_planner import TimingPlanner


def test_timing_planner_keeps_sentence_boundaries_but_batches_into_paragraph_blocks():
    frames = [
        StoryboardFrame(index=0, narration="Sentence 1.", image_prompt="p1"),
        StoryboardFrame(index=1, narration="Sentence 2.", image_prompt="p2"),
        StoryboardFrame(index=2, narration="Sentence 3.", image_prompt="p3"),
    ]

    planner = TimingPlanner(mode="paragraph", max_sentences=2, max_chars=40)
    plan = planner.build(frames)

    assert [s.text for s in plan.sentences] == [
        "Sentence 1.",
        "Sentence 2.",
        "Sentence 3.",
    ]
    assert [b.text for b in plan.blocks] == ["Sentence 1. Sentence 2.", "Sentence 3."]
    assert [b.source_frame_indices for b in plan.blocks] == [[0, 1], [2]]
    assert [s.block_id for s in plan.sentences] == ["block-1", "block-1", "block-2"]


def test_timing_planner_splits_multiple_sentences_within_one_frame():
    frames = [
        StoryboardFrame(
            index=0,
            narration='Version 2.1 is out. He said, "Go." Then left. 第一段。第二段！',
            image_prompt="p1",
        ),
        StoryboardFrame(index=1, narration="Third sentence.", image_prompt="p2"),
    ]

    planner = TimingPlanner(mode="paragraph", max_sentences=2, max_chars=80)
    plan = planner.build(frames)

    assert [s.text for s in plan.sentences] == [
        "Version 2.1 is out.",
        'He said, "Go."',
        "Then left.",
        "第一段。",
        "第二段！",
        "Third sentence.",
    ]
    assert [s.frame_indices for s in plan.sentences] == [[0], [0], [0], [0], [0], [1]]
    assert [b.text for b in plan.blocks] == [
        'Version 2.1 is out. He said, "Go."',
        "Then left. 第一段。",
        "第二段！ Third sentence.",
    ]
    assert [b.source_frame_indices for b in plan.blocks] == [[0, 0], [0, 0], [0, 1]]


def test_timing_planner_sentence_mode_keeps_each_sentence_in_its_own_block():
    frames = [
        StoryboardFrame(index=3, narration="Sentence 1.", image_prompt="p1"),
        StoryboardFrame(index=7, narration="Sentence 2.", image_prompt="p2"),
    ]

    planner = TimingPlanner(mode="sentence", max_sentences=8, max_chars=120)
    plan = planner.build(frames)

    assert [b.text for b in plan.blocks] == ["Sentence 1.", "Sentence 2."]
    assert [b.source_frame_indices for b in plan.blocks] == [[3], [7]]


def test_timing_planner_respects_max_chars_when_grouping_blocks():
    frames = [
        StoryboardFrame(index=0, narration="Alpha beta.", image_prompt="p1"),
        StoryboardFrame(index=1, narration="Gamma delta.", image_prompt="p2"),
        StoryboardFrame(index=2, narration="Epsilon zeta.", image_prompt="p3"),
    ]

    planner = TimingPlanner(mode="paragraph", max_sentences=10, max_chars=25)
    plan = planner.build(frames)

    assert [b.text for b in plan.blocks] == ["Alpha beta. Gamma delta.", "Epsilon zeta."]
    assert [b.source_frame_indices for b in plan.blocks] == [[0, 1], [2]]


def test_timing_planner_splits_no_space_english_boundary_within_single_frame():
    frames = [
        StoryboardFrame(index=0, narration="Wait!Another sentence.", image_prompt="p1"),
    ]

    planner = TimingPlanner(mode="paragraph", max_sentences=8, max_chars=80)
    plan = planner.build(frames)

    assert [s.text for s in plan.sentences] == ["Wait!", "Another sentence."]
    assert [s.frame_indices for s in plan.sentences] == [[0], [0]]
    assert [b.text for b in plan.blocks] == ["Wait! Another sentence."]
    assert [b.source_frame_indices for b in plan.blocks] == [[0, 0]]
