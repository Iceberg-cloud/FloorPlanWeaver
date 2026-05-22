"""Test modification intent: room_program preservation, position hints, regeneration."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.planner_agent import PlannerAgent
from app.services.requirement_memory import apply_delta_to_memory, snapshot_from_final_plan
from app.services.default_semantic_layout import build_default_semantic_plan, _extract_prefer_edge
from app.schemas.session import ChatMessage
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem, AdjacencyRule


def _make_8room_collected() -> dict:
    """Simulate collected requirements from a rich first message."""
    agent = PlannerAgent()
    msg = ("四室两厅住宅，140平米，南向，三代同堂，"
           "需要主卧套间、两个次卧、一个书房兼客房、"
           "客厅、餐厅、厨房、两个卫生间、大阳台，动静分离")
    collected = {}
    agent._extract_to_collected(msg, collected)
    return collected


# ── Modification detection ──────────────────────────────────────

def test_modification_detected_move():
    agent = PlannerAgent()
    assert bool(agent._MODIFICATION_PATTERN.search("请将厨房移动至右下角"))
    assert bool(agent._MODIFICATION_PATTERN.search("把厨房移到左边"))
    assert bool(agent._MODIFICATION_PATTERN.search("将主卧放到右上角"))


def test_modification_detected_change():
    agent = PlannerAgent()
    assert bool(agent._MODIFICATION_PATTERN.search("改一下厨房的位置"))
    assert bool(agent._MODIFICATION_PATTERN.search("调整客厅面积"))


def test_modification_not_detected_new():
    agent = PlannerAgent()
    assert not bool(agent._MODIFICATION_PATTERN.search("三居室120平米，客厅厨房卫生间"))
    assert not bool(agent._MODIFICATION_PATTERN.search("我要一个书房"))


# ── Room program preservation ───────────────────────────────────

def test_modification_preserves_rooms():
    collected = _make_8room_collected()
    original_count = len(collected.get("room_program", []))
    assert original_count == 8

    agent = PlannerAgent()
    agent._extract_to_collected("请将厨房移动至右下角", collected)
    assert len(collected.get("room_program", [])) == original_count


def test_modification_preserves_rooms_via_apply_delta():
    collected = _make_8room_collected()
    original_count = len(collected.get("room_program", []))
    assert original_count == 8

    working = apply_delta_to_memory(collected, "请将厨房移动至右下角")
    assert len(working.get("room_program", [])) == original_count


def test_new_description_replaces_rooms():
    collected = {}
    agent = PlannerAgent()
    agent._extract_to_collected("两居室，客厅厨房卫生间", collected)
    assert len(collected.get("room_program", [])) == 3

    # New description should replace
    agent._extract_to_collected("三居室，客厅餐厅厨房主卧次卧卫生间阳台书房", collected)
    rooms = collected.get("room_program", [])
    assert len(rooms) >= 5  # New rooms replaced old ones


# ── Position hint injection ─────────────────────────────────────

def test_position_hint_injected():
    collected = _make_8room_collected()
    agent = PlannerAgent()
    agent._extract_to_collected("请将厨房移动至右下角", collected)

    rooms = collected.get("room_program", [])
    kitchen = next(r for r in rooms if r.get("room_type") == "厨房")
    assert "右下角" in kitchen.get("notes", "")


def test_position_hint_injected_via_apply_delta():
    collected = _make_8room_collected()
    working = apply_delta_to_memory(collected, "请将厨房移到上方")

    rooms = working.get("room_program", [])
    kitchen = next(r for r in rooms if r.get("room_type") == "厨房")
    assert "上方" in kitchen.get("notes", "")


def test_non_mentioned_rooms_no_position():
    collected = _make_8room_collected()
    agent = PlannerAgent()
    agent._extract_to_collected("请将厨房移动至右下角", collected)

    rooms = collected.get("room_program", [])
    bedroom = next(r for r in rooms if r.get("room_type") == "主卧")
    assert "右下角" not in bedroom.get("notes", "")


# ── Extract prefer edge ─────────────────────────────────────────

def test_extract_prefer_edge_south():
    assert _extract_prefer_edge("用户要求：右下角", "厨房") == "south"
    assert _extract_prefer_edge("用户要求：南侧", "厨房") == "south"


def test_extract_prefer_edge_north():
    assert _extract_prefer_edge("用户要求：右上角", "书房") == "north"


def test_extract_prefer_edge_east():
    assert _extract_prefer_edge("用户要求：右侧", "主卧") == "east"


def test_extract_prefer_edge_west():
    assert _extract_prefer_edge("用户要求：左", "卫生间") == "west"


def test_extract_prefer_edge_default():
    assert _extract_prefer_edge("", "客厅") == "south"
    assert _extract_prefer_edge("", "阳台") == "south"
    assert _extract_prefer_edge("", "厨房") == "west"


# ── Full regeneration flow ──────────────────────────────────────

def test_full_regen_flow_preserves_rooms_and_hints():
    """Simulate complete turn1 → regenerate → turn2 flow."""
    # Turn 1: full description
    agent = PlannerAgent()
    msg1 = ("四室两厅住宅，140平米，南向，"
            "主卧、两个次卧、书房、客厅、餐厅、厨房、两个卫生间、大阳台")
    out1 = agent.run(msg1, collected={}, ask_count=0)
    assert isinstance(out1, PlannerFinalPlan)
    assert len(out1.space_program) == 8

    # Snapshot from turn 1
    snap = snapshot_from_final_plan(out1)
    assert len(snap.get("room_program", [])) == 8

    # Turn 2: modification
    msg2 = "请将厨房移动至右下角"
    working = apply_delta_to_memory(snap, msg2)
    assert len(working.get("room_program", [])) == 8

    # Kitchen should have position hint
    rooms = working.get("room_program", [])
    kitchen = next(r for r in rooms if r.get("room_type") == "厨房")
    assert "右下角" in kitchen.get("notes", "")

    # Generate final plan from modification
    out2 = agent.run(msg2, collected=working, ask_count=1, force_finalize=True)
    assert isinstance(out2, PlannerFinalPlan)
    assert len(out2.space_program) == 8

    # Kitchen in final plan should have position hint
    kitchen_sp = next(sp for sp in out2.space_program if sp.room_type == "厨房")
    assert "右下角" in kitchen_sp.notes


def test_regen_via_build_default_semantic():
    """Verify default semantic plan respects position hints."""
    agent = PlannerAgent()
    msg1 = ("四居室住宅，140平米，南向，"
            "客厅、餐厅、厨房、主卧、次卧、书房、卫生间、阳台")
    out1 = agent.run(msg1, collected={}, ask_count=0)
    assert isinstance(out1, PlannerFinalPlan)

    snap = snapshot_from_final_plan(out1)
    working = apply_delta_to_memory(snap, "请将厨房移到右下角")
    out2 = agent.run("请将厨房移到右下角", collected=working, ask_count=1, force_finalize=True)

    # Build default semantic plan
    from app.schemas.layout import SiteOutline, Point2D
    outline = SiteOutline(
        vertices=[Point2D(x=0, y=0), Point2D(x=14, y=0),
                  Point2D(x=14, y=10), Point2D(x=0, y=10)],
        entrance_edge=[0, 1], total_area_sqm=140,
        bounding_box={"width": 14, "height": 10}, unit="meter",
    )
    semantic = build_default_semantic_plan(out2)

    # Find kitchen placement
    kitchen_p = next((p for p in semantic.placements if p.room_type == "厨房"), None)
    assert kitchen_p is not None
    # Kitchen should prefer south edge (bottom = south in our coordinate system)
    assert kitchen_p.prefer_edge == "south"
