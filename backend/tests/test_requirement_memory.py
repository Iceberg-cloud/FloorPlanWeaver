import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.planner_agent import PlannerAgent
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem
from app.schemas.session import ChatMessage
from app.services.requirement_memory import (
    apply_delta_to_memory,
    build_planner_messages,
    build_regenerate_user_message,
    compute_missing_fields,
    filter_missing_fields,
    merge_room_program,
    merge_snapshot,
    reconcile_final_plan,
    snapshot_from_final_plan,
)


def test_apply_delta_extracts_area_and_layout():
    mem = apply_delta_to_memory({}, "我想做一套三居室，大约120平米，南向")
    assert mem.get("layout_type") == "三居"
    assert mem.get("target_area_sqm") == 120
    assert mem.get("orientation")


def test_merge_snapshot_keeps_prior_fields():
    base = {"layout_type": "三居", "target_area_sqm": 120}
    merged = merge_snapshot(base, {"orientation": "南向优先", "building_type": "住宅"})
    assert merged["layout_type"] == "三居"
    assert merged["target_area_sqm"] == 120
    assert merged["orientation"] == "南向优先"


def test_merge_room_program_updates_counts():
    existing = [{"room_type": "次卧", "count": 1, "target_area_sqm": 10}]
    new = [{"room_type": "次卧", "count": 2, "target_area_sqm": 12}]
    out = merge_room_program(existing, new)
    assert len(out) == 1
    assert out[0]["count"] == 2


def test_filter_missing_fields_drops_filled():
    memory = apply_delta_to_memory({}, "三居 120平 南向 住宅")
    memory["room_program"] = [{"room_type": "客厅", "count": 1, "target_area_sqm": 20}]
    missing = filter_missing_fields(
        ["target_area_sqm", "layout_type", "room_program", "orientation"],
        memory,
    )
    assert "target_area_sqm" not in missing
    assert "layout_type" not in missing


def test_build_planner_messages_includes_history():
    history = [
        ChatMessage(role="user", content="三居室"),
        ChatMessage(role="assistant", content="请补充面积"),
    ]
    msgs = build_planner_messages(
        working_memory={"layout_type": "三居"},
        user_message="120平米",
        chat_history=history,
    )
    assert len(msgs) == 3
    assert msgs[0]["content"] == "三居室"
    assert "120平米" in msgs[-1]["content"]
    assert "已确认需求快照" in msgs[-1]["content"]


def test_multiturn_memory_no_repeat_missing():
    agent = PlannerAgent()
    mem: dict = {}
    mem = apply_delta_to_memory(mem, "设计房子")
    out1 = agent.run("设计房子", collected=mem)
    assert out1.agent_state == "ASK_FOR_MORE"
    mem = merge_snapshot(mem, out1.collected_snapshot)

    mem = apply_delta_to_memory(mem, "三居，120平米，南向")
    missing = compute_missing_fields(mem)
    assert "target_area_sqm" not in missing
    assert "layout_type" not in missing
    out2 = agent.run("三居，120平米，南向", collected=mem, ask_count=1, force_finalize=True)
    assert out2.agent_state == "FINAL_PLAN"


def test_snapshot_from_final_plan_roundtrip():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="公寓", target_area_sqm=90, layout_type="三居", orientation="南向",
        ),
        design_goals=["采光好"],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=20),
        ],
        adjacency_graph=[],
        drawing_brief="测试方案",
    )
    snap = snapshot_from_final_plan(plan)
    assert snap["target_area_sqm"] == 90
    assert snap["room_program"][0]["room_type"] == "客厅"


def test_build_regenerate_includes_memory():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="公寓", target_area_sqm=80, layout_type="两居", orientation="南向",
        ),
        design_goals=[],
        space_program=[SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=18)],
        adjacency_graph=[],
        drawing_brief="原方案",
    )
    msg = build_regenerate_user_message(plan, "增加书房", {"layout_type": "两居"})
    assert "书房" in msg
    assert "原方案" in msg
    assert "两居" in msg
