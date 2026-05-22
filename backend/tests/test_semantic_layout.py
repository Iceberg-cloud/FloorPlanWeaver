import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.layout import Point2D, SiteOutline
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem
from app.schemas.semantic_layout import AdjacencyIntent, LayoutBand, RoomPlacement, SemanticLayoutPlan
from app.services.default_semantic_layout import build_default_semantic_plan
from app.services.layout_compiler import compile_semantic_layout
from app.services.layout_postprocess import postprocess_layout
from app.services.layout_validator import validate_layout
from app.services.semantic_validator import validate_semantic_plan


def _plan():
    return PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(building_type="公寓", target_area_sqm=45, layout_type="一居", orientation="南向"),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=12),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=10),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=6),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=4),
            SpaceProgramItem(room_type="阳台", count=1, target_area_sqm=4),
        ],
        adjacency_graph=[], drawing_brief="test",
    )


def _outline():
    return SiteOutline(
        vertices=[Point2D(x=0, y=0), Point2D(x=9, y=0), Point2D(x=9, y=5), Point2D(x=0, y=5)],
        entrance_edge=[0, 1], total_area_sqm=45, bounding_box={"width": 9, "height": 5}, unit="m",
    )


def test_semantic_strip_bands_compile():
    plan = _plan()
    semantic = SemanticLayoutPlan(
        layout_style="strip", strip_direction="horizontal",
        bands=[LayoutBand(order=["阳台", "客厅"]), LayoutBand(order=["厨房", "主卧", "卫生间"])],
        placements=[],
    )
    assert validate_semantic_plan(plan, semantic) == []
    layout, _ = compile_semantic_layout(semantic, plan, _outline())
    layout, _ = postprocess_layout(layout, _outline(), plan)
    assert len(layout.rooms) == 5
    names = [r.name for r in layout.rooms]
    assert "客厅" in names and "主卧" in names
    v = validate_layout(layout, _outline(), plan)
    assert v.hard_constraints_passed


def test_default_semantic_has_bands():
    plan = _plan()
    semantic = build_default_semantic_plan(plan)
    assert semantic.bands
    layout, _ = compile_semantic_layout(semantic, plan, _outline())
    assert len(layout.rooms) >= 3


def test_greedy_small_rooms_in_corners():
    plan = _plan()
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout(semantic, plan, _outline())
    layout, _ = postprocess_layout(layout, _outline(), plan)
    v = validate_layout(layout, _outline(), plan)
    assert v.hard_constraints_passed, f"Hard constraints failed: {v.errors}"


def test_living_room_is_polygon_kind():
    plan = _plan()
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout(semantic, plan, _outline())
    layout, _ = postprocess_layout(layout, _outline(), plan)
    living = next((r for r in layout.rooms if r.name == "客厅"), None)
    assert living is not None
    assert living.shape_kind == "polygon"
    assert len(living.polygon) >= 4


def test_regular_rooms_remain_rectangular():
    plan = _plan()
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout(semantic, plan, _outline())
    layout, _ = postprocess_layout(layout, _outline(), plan)
    regular_types = {"卫生间", "主卧", "次卧", "厨房", "阳台", "走廊"}
    polygon_types = {"客厅", "餐厅", "书房", "起居室", "客餐厅"}
    for room in layout.rooms:
        if room.name in polygon_types:
            assert room.shape_kind == "polygon", f"{room.name} should be polygon"
            continue
        if room.name in regular_types:
            assert len(room.polygon) == 4, f"{room.name} should be rectangular but has {len(room.polygon)} vertices"


def test_study_room_is_polygon_not_bedroom_rect():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(building_type="公寓", target_area_sqm=55, layout_type="二居", orientation="南向"),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=14),
            SpaceProgramItem(room_type="餐厅", count=1, target_area_sqm=8),
            SpaceProgramItem(room_type="书房", count=1, target_area_sqm=8),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=12),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=6),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=4),
        ],
        adjacency_graph=[], drawing_brief="test",
    )
    outline = SiteOutline(
        vertices=[Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=6), Point2D(x=0, y=6)],
        entrance_edge=[0, 1], total_area_sqm=60, bounding_box={"width": 10, "height": 6}, unit="m",
    )
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout(semantic, plan, outline)
    layout, _ = postprocess_layout(layout, outline, plan)
    study = next((r for r in layout.rooms if r.name == "书房"), None)
    assert study is not None
    assert study.shape_kind == "polygon"
    v = validate_layout(layout, outline, plan)
    assert v.hard_constraints_passed, v.errors


def test_rooms_snap_to_outline_boundary():
    plan = _plan()
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout(semantic, plan, _outline())
    layout, _ = postprocess_layout(layout, _outline(), plan)
    v = validate_layout(layout, _outline(), plan)
    assert v.hard_constraints_passed, f"Validation failed: {v.errors}"


def test_greedy_l_shape_layout():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(building_type="公寓", target_area_sqm=36, layout_type="一居", orientation="南向"),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=12),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=10),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=6),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=4),
        ],
        adjacency_graph=[], drawing_brief="test",
    )
    outline = SiteOutline(
        vertices=[Point2D(x=0,y=0),Point2D(x=8,y=0),Point2D(x=8,y=3),Point2D(x=4,y=3),Point2D(x=4,y=6),Point2D(x=0,y=6)],
        entrance_edge=[0,1], total_area_sqm=36, bounding_box={"width":8,"height":6}, unit="m",
    )
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout(semantic, plan, outline)
    layout, _ = postprocess_layout(layout, outline, plan)
    assert len(layout.rooms) >= 4
    v = validate_layout(layout, outline, plan)
    assert v.hard_constraints_passed, f"L-shape failed: {v.errors}"


def test_l_shape_flexible_fills_concavity():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(building_type="公寓", target_area_sqm=36, layout_type="一居", orientation="南向"),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=14),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=10),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=6),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=4),
        ],
        adjacency_graph=[], drawing_brief="test",
    )
    outline = SiteOutline(
        vertices=[Point2D(x=0,y=0),Point2D(x=8,y=0),Point2D(x=8,y=3),Point2D(x=4,y=3),Point2D(x=4,y=6),Point2D(x=0,y=6)],
        entrance_edge=[0,1], total_area_sqm=36, bounding_box={"width":8,"height":6}, unit="m",
    )
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout(semantic, plan, outline)
    layout, _ = postprocess_layout(layout, outline, plan)
    v = validate_layout(layout, outline, plan)
    assert v.hard_constraints_passed, f"L-shape validation failed: {v.errors}"


def test_7room_plan_coverage():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(building_type="公寓", target_area_sqm=96, layout_type="三居", orientation="南向"),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=20),
            SpaceProgramItem(room_type="餐厅", count=1, target_area_sqm=10),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=14),
            SpaceProgramItem(room_type="次卧", count=1, target_area_sqm=10),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=6),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=5),
            SpaceProgramItem(room_type="阳台", count=1, target_area_sqm=4),
        ],
        adjacency_graph=[], drawing_brief="test",
    )
    outline = SiteOutline(
        vertices=[Point2D(x=0,y=0),Point2D(x=12,y=0),Point2D(x=12,y=8),Point2D(x=0,y=8)],
        entrance_edge=[0,1], total_area_sqm=96, bounding_box={"width":12,"height":8}, unit="m",
    )
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout(semantic, plan, outline)
    layout, _ = postprocess_layout(layout, outline, plan)
    assert len(layout.rooms) >= 4
    v = validate_layout(layout, outline, plan)
    assert v.hard_constraints_passed, f"7-room validation failed: {v.errors}"
    total_area = sum(r.area_sqm for r in layout.rooms)
    coverage = total_area / outline.total_area_sqm
    assert coverage >= 0.30, f"7-room coverage {coverage:.1%} too low"


def test_grid_aligns_duplicate_room_types_with_program():
    plan = PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(building_type="公寓", target_area_sqm=80, layout_type="三居", orientation="南向"),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type="客厅", count=1, target_area_sqm=18),
            SpaceProgramItem(room_type="主卧", count=1, target_area_sqm=14),
            SpaceProgramItem(room_type="次卧", count=2, target_area_sqm=10),
            SpaceProgramItem(room_type="厨房", count=1, target_area_sqm=6),
            SpaceProgramItem(room_type="卫生间", count=1, target_area_sqm=5),
        ],
        adjacency_graph=[], drawing_brief="test",
    )
    outline = SiteOutline(
        vertices=[Point2D(x=0,y=0),Point2D(x=10,y=0),Point2D(x=10,y=8),Point2D(x=0,y=8)],
        entrance_edge=[0,1], total_area_sqm=80, bounding_box={"width":10,"height":8}, unit="m",
    )
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout(semantic, plan, outline)
    assert layout.compile_method in ("grid", "grid_search")
    assert len(layout.rooms) == 6
    names = {r.name for r in layout.rooms}
    assert "次卧1" in names and "次卧2" in names
    assert sum(1 for r in layout.rooms if r.type == "次卧") == 2
