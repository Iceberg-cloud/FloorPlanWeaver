"""Test cross-turn memory: user preferences from history, conversation summary, merge."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.session import ChatMessage
from app.services.requirement_memory import (
    apply_delta_to_memory,
    extract_user_preferences,
    merge_snapshot,
    merge_string_list,
    build_planner_messages,
    snapshot_from_final_plan,
)


def test_extract_preferences_single_message():
    prefs = extract_user_preferences("我家里有老人和小孩，需要无障碍设计")
    assert "有老人居住" in prefs
    assert "有小孩" in prefs
    assert "需要无障碍设计" in prefs


def test_extract_preferences_room_size():
    prefs = extract_user_preferences("主卧要大一点，厨房要明亮")
    assert "主卧要宽敞" in prefs
    # "厨房要明亮" doesn't match the exact pattern, only "厨房要大" does
    assert "厨房要大" not in prefs


def test_extract_preferences_island():
    prefs = extract_user_preferences("厨房要放岛台，卫生间干湿分离")
    assert "厨房要放岛台" in prefs
    assert "卫生间干湿分离" in prefs


def test_apply_delta_extracts_preferences():
    mem = apply_delta_to_memory({}, "三居120平，有宠物，主卧要大")
    assert mem.get("layout_type") == "三居"
    assert mem.get("target_area_sqm") == 120
    prefs = mem.get("user_preferences") or []
    assert "有宠物" in prefs
    assert "主卧要宽敞" in prefs


def test_apply_delta_extracts_preferences_from_history():
    history = [
        ChatMessage(role="user", content="家里有老人，需要无障碍"),
        ChatMessage(role="assistant", content="好的"),
    ]
    mem = apply_delta_to_memory({}, "三居120平", chat_history=history)
    prefs = mem.get("user_preferences") or []
    assert "有老人居住" in prefs
    assert "需要无障碍设计" in prefs


def test_apply_delta_builds_conversation_summary():
    history = [
        ChatMessage(role="user", content="我要三居室"),
        ChatMessage(role="assistant", content="好的，请问面积？"),
    ]
    mem = apply_delta_to_memory({}, "120平", chat_history=history)
    summary = mem.get("conversation_summary") or ""
    assert "用户：我要三居室" in summary
    assert "助手：好的" in summary


def test_apply_delta_merges_preferences_across_turns():
    """Preferences from turn 1 persist when turn 2 adds new ones."""
    mem1 = apply_delta_to_memory({}, "有宠物，需要书房")
    assert "有宠物" in mem1.get("user_preferences", [])
    assert "需要书房" in mem1.get("user_preferences", [])

    # Turn 2: new preferences merge with existing
    mem2 = apply_delta_to_memory(mem1, "主卧要大，干湿分离")
    prefs = mem2.get("user_preferences") or []
    assert "有宠物" in prefs  # from turn 1
    assert "需要书房" in prefs  # from turn 1
    assert "主卧要宽敞" in prefs  # from turn 2
    assert "卫生间干湿分离" in prefs  # from turn 2


def test_merge_snapshot_preserves_preferences():
    base = {"user_preferences": ["有宠物", "需要书房"]}
    update = {"user_preferences": ["主卧要宽敞", "有宠物"]}
    merged = merge_snapshot(base, update)
    prefs = merged.get("user_preferences") or []
    assert "有宠物" in prefs
    assert "需要书房" in prefs
    assert "主卧要宽敞" in prefs
    assert len(prefs) == 3  # deduplicated


def test_merge_string_list_dedup():
    result = merge_string_list(["a", "b"], ["b", "c"])
    assert result == ["a", "b", "c"]


def test_build_planner_messages_includes_preferences():
    mem = {
        "layout_type": "三居",
        "target_area_sqm": 120,
        "user_preferences": ["有宠物", "需要无障碍设计"],
    }
    msgs = build_planner_messages(
        working_memory=mem,
        user_message="请帮我设计",
        chat_history=[],
    )
    # Last message should contain preferences
    last_content = msgs[-1]["content"]
    assert "【用户偏好】" in last_content
    assert "有宠物" in last_content
    assert "需要无障碍设计" in last_content


def test_build_planner_messages_includes_conversation_summary():
    mem = {
        "layout_type": "三居",
        "conversation_summary": "用户：我要三居室\n助手：好的",
    }
    msgs = build_planner_messages(
        working_memory=mem,
        user_message="120平",
        chat_history=[],
    )
    last_content = msgs[-1]["content"]
    assert "【历史对话摘要】" in last_content
    assert "用户：我要三居室" in last_content


def test_build_planner_messages_without_preferences():
    mem = {"layout_type": "三居", "target_area_sqm": 120}
    msgs = build_planner_messages(
        working_memory=mem,
        user_message="请设计",
        chat_history=[],
    )
    last_content = msgs[-1]["content"]
    assert "【用户偏好】" not in last_content
    assert "【历史对话摘要】" not in last_content


def test_full_multi_turn_flow():
    """Simulate a 3-turn conversation and verify all information is retained."""
    # Turn 1
    history1 = []
    mem1 = apply_delta_to_memory({}, "我要三居室住宅", chat_history=history1)
    assert mem1.get("layout_type") == "三居"
    assert mem1.get("building_type") == "住宅"

    # Turn 2
    history2 = [ChatMessage(role="user", content="我要三居室住宅"), ChatMessage(role="assistant", content="好的")]
    mem2 = apply_delta_to_memory(mem1, "120平，有老人和小孩", chat_history=history2)
    assert mem2.get("target_area_sqm") == 120
    prefs2 = mem2.get("user_preferences") or []
    assert "有老人居住" in prefs2
    assert "有小孩" in prefs2
    # Turn 1's structure is retained
    assert mem2.get("layout_type") == "三居"

    # Turn 3
    history3 = history2 + [
        ChatMessage(role="user", content="120平，有老人和小孩"),
        ChatMessage(role="assistant", content="已记录"),
    ]
    mem3 = apply_delta_to_memory(mem2, "主卧要大一点，需要书房，南向", chat_history=history3)
    assert mem3.get("orientation") == "南向优先"
    prefs3 = mem3.get("user_preferences") or []
    assert "主卧要宽敞" in prefs3
    assert "需要书房" in prefs3
    # Turn 2 preferences are still there
    assert "有老人居住" in prefs3
    assert "有小孩" in prefs3
    # Conversation summary includes turn 1 and turn 2
    summary = mem3.get("conversation_summary") or ""
    assert "三居室" in summary
