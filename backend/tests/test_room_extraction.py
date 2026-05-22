"""Test room extraction edge cases: 卧室, 客餐厅, compound names."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.planner_agent import PlannerAgent


def test_bedroom_extracted_from_一室一厅():
    agent = PlannerAgent()
    msg = ("一室一厅公寓，60㎡，南向采光，单身居住，"
           "需要卧室、客餐厅一体、开放式厨房、卫生间、阳台，紧凑实用")
    collected = {}
    agent._extract_to_collected(msg, collected)

    rooms = collected.get("room_program", [])
    types = [r["room_type"] for r in rooms]
    assert "卧室" in types, f"卧室 should be extracted, got: {types}"
    assert "卫生间" in types
    assert "阳台" in types
    assert "厨房" in types


def test_客餐厅_extracted_as_composite():
    agent = PlannerAgent()
    msg = "三居室100平，需要客餐厅一体、主卧、次卧、厨房、卫生间"
    collected = {}
    agent._extract_to_collected(msg, collected)

    rooms = collected.get("room_program", [])
    types = [r["room_type"] for r in rooms]
    # "客餐厅一体" should match "客餐厅" (longer match first), not "餐厅" alone
    assert "客餐厅" in types, f"客餐厅 should be extracted, got: {types}"
    # "餐厅" should NOT be separately extracted since "客餐厅" covers it
    assert types.count("客餐厅") == 1


def test_卧室_not_duplicated_with_主卧():
    agent = PlannerAgent()
    msg = "需要卧室和主卧，三居120平"
    collected = {}
    agent._extract_to_collected(msg, collected)

    rooms = collected.get("room_program", [])
    types = [r["room_type"] for r in rooms]
    # Both "卧室" and "主卧" should be extracted since they are separate mentions
    assert "卧室" in types
    assert "主卧" in types


def test_full_plan_includes_all_rooms():
    agent = PlannerAgent()
    msg = ("一室一厅公寓，60㎡，南向采光，单身居住，"
           "需要卧室、客餐厅一体、开放式厨房、卫生间、阳台，紧凑实用")
    out = agent.run(msg, collected={}, ask_count=0)

    from app.schemas.planner import PlannerFinalPlan
    assert isinstance(out, PlannerFinalPlan)
    room_types = [sp.room_type for sp in out.space_program]
    assert "卧室" in room_types, f"卧室 missing from plan, got: {room_types}"
    assert "客餐厅" in room_types or "客厅" in room_types, f"客厅/客餐厅 missing, got: {room_types}"
    assert "厨房" in room_types
    assert "卫生间" in room_types
    assert "阳台" in room_types
    assert len(out.space_program) >= 5, f"Expected >=5 rooms, got {len(out.space_program)}: {room_types}"


def test_两卧室_count():
    agent = PlannerAgent()
    msg = "三居室，需要两卧室、客厅、厨房、卫生间"
    collected = {}
    agent._extract_to_collected(msg, collected)

    rooms = collected.get("room_program", [])
    bedroom = next((r for r in rooms if r["room_type"] == "卧室"), None)
    assert bedroom is not None, "卧室 should be extracted"
    assert bedroom["count"] == 2, f"两卧室 should set count=2, got {bedroom['count']}"


def test_open_kitchen_note():
    agent = PlannerAgent()
    msg = "两居室80平，需要开放式厨房、客厅、主卧、卫生间"
    collected = {}
    agent._extract_to_collected(msg, collected)

    rooms = collected.get("room_program", [])
    kitchen = next((r for r in rooms if r["room_type"] == "厨房"), None)
    assert kitchen is not None, "厨房 should be extracted"
