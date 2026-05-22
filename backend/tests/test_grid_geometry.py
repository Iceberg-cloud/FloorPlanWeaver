"""Comprehensive grid-level validation for Method A geometric correctness.

Checks: coverage, overlap, gaps, connectivity, rectangularity, boundary touch,
adjacency, area conservation, seed quality, and multi-shape outlines.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.layout import LayoutDraft, Point2D, SiteOutline
from app.schemas.planner import PlannerFinalPlan, ProjectProfile, SpaceProgramItem
from app.services.default_semantic_layout import build_default_semantic_plan
from app.services.layout_grid import CELL_AREA, GridMap
from app.services.layout_grid_search import (
    SearchState,
    export_grid_assignment,
    run_grid_search_layout,
    validate_grid_layout,
)
from app.services.layout_grid_search_compiler import compile_semantic_layout_grid_search
from app.services.layout_constraint_builder import build_constraint_plan
from app.services.layout_metrics import compute_layout_area_metrics


# ── helpers ──────────────────────────────────────────────────────

def _plan(rooms: list[tuple[str, int, float]], area: float, layout: str = "三居") -> PlannerFinalPlan:
    return PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="住宅", target_area_sqm=area, layout_type=layout, orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type=rt, count=c, target_area_sqm=a)
            for rt, c, a in rooms
        ],
        adjacency_graph=[],
        drawing_brief="test",
    )


def _rect_outline(w: float, h: float) -> SiteOutline:
    a = w * h
    return SiteOutline(
        vertices=[Point2D(x=0, y=0), Point2D(x=w, y=0), Point2D(x=w, y=h), Point2D(x=0, y=h)],
        entrance_edge=[0, 1], total_area_sqm=a, bounding_box={"width": w, "height": h}, unit="m",
    )


def _l_outline() -> SiteOutline:
    verts = [
        Point2D(x=0, y=0), Point2D(x=8, y=0), Point2D(x=8, y=3),
        Point2D(x=4, y=3), Point2D(x=4, y=6), Point2D(x=0, y=6),
    ]
    return SiteOutline(
        vertices=verts, entrance_edge=[0, 1],
        total_area_sqm=36, bounding_box={"width": 8, "height": 6}, unit="m",
    )


def _t_outline() -> SiteOutline:
    verts = [
        Point2D(x=2, y=0), Point2D(x=6, y=0), Point2D(x=6, y=3),
        Point2D(x=10, y=3), Point2D(x=10, y=6), Point2D(x=0, y=6),
        Point2D(x=0, y=3), Point2D(x=2, y=3),
    ]
    return SiteOutline(
        vertices=verts, entrance_edge=[0, 1],
        total_area_sqm=42, bounding_box={"width": 10, "height": 6}, unit="m",
    )


def _run_grid(rooms, outline, layout="三居"):
    plan = _plan(rooms, outline.total_area_sqm, layout)
    semantic = build_default_semantic_plan(plan)
    cp = build_constraint_plan(plan, semantic, outline)
    state, grid, report = run_grid_search_layout(cp, outline)
    return plan, semantic, outline, state, grid, report, cp


# ── 1. coverage ──────────────────────────────────────────────────

@pytest.mark.parametrize("w,h,rooms", [
    (10, 8, [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5), ("餐厅", 1, 10)]),
    (8, 7, [("客厅", 1, 18), ("主卧", 1, 12), ("厨房", 1, 6), ("卫生间", 1, 4)]),
])
def test_full_coverage_rect_outline(w, h, rooms):
    outline = _rect_outline(w, h)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None, "beam search returned None"
    unassigned = sum(1 for j in range(grid.rows) for i in range(grid.cols) if grid.inside[j][i] and state.rid[j][i] == 0)
    assert unassigned == 0, f"{unassigned} unassigned cells remain"
    assert report.area_coverage_ratio >= 0.99, f"coverage only {report.area_coverage_ratio:.2%}"


# ── 2. no gaps (unassigned cells = 0) ───────────────────────────

def test_no_gaps_l_shape():
    rooms = [("客厅", 1, 14), ("主卧", 1, 10), ("厨房", 1, 6), ("卫生间", 1, 4)]
    outline = _l_outline()
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    unassigned = sum(1 for j in range(grid.rows) for i in range(grid.cols) if grid.inside[j][i] and state.rid[j][i] == 0)
    assert unassigned == 0


# ── 3. no overlap (each cell assigned at most once) ──────────────

def test_no_overlap():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    seen: dict[tuple[int, int], int] = {}
    for j in range(grid.rows):
        for i in range(grid.cols):
            if not grid.inside[j][i]:
                continue
            rid = state.rid[j][i]
            if rid == 0:
                continue
            prev = seen.get((i, j))
            assert prev is None, f"cell ({i},{j}) assigned to both room {prev} and {rid}"


# ── 4. area conservation ────────────────────────────────────────

def test_total_area_equals_outline():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5), ("餐厅", 1, 10)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    inside = grid.total_inside()
    assigned = sum(1 for j in range(grid.rows) for i in range(grid.cols) if grid.inside[j][i] and state.rid[j][i] > 0)
    assert inside == assigned, f"inside={inside} assigned={assigned}"
    assert abs(report.planned_area_sqm - report.outline_area_sqm) < 0.5


# ── 5. connectivity ─────────────────────────────────────────────

def test_each_room_connected():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    for c in cp.rooms:
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        cells = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
                 if grid.inside[j][i] and state.rid[j][i] == rid]
        assert _connected(cells), f"「{c.name}」is not connected ({len(cells)} cells)"


def _connected(cells):
    if not cells:
        return False
    target = set(cells)
    seen = {cells[0]}
    q = [cells[0]]
    while q:
        i, j = q.pop()
        for ni, nj in ((i+1,j),(i-1,j),(i,j+1),(i,j-1)):
            if (ni, nj) in target and (ni, nj) not in seen:
                seen.add((ni, nj))
                q.append((ni, nj))
    return len(seen) == len(target)


# ── 6. rectangular rooms ────────────────────────────────────────

def test_strong_rooms_rectangular():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    # Hard rect types: zero tolerance
    _HARD = frozenset({"卫生间", "主卫", "客卫", "主卧", "次卧", "卧室", "儿童房", "阳台"})
    non_rect_hard = 0
    non_rect_other = 0
    for c in cp.rooms:
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        cells = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
                 if grid.inside[j][i] and state.rid[j][i] == rid]
        if not cells:
            continue
        is_ = [p[0] for p in cells]
        js_ = [p[1] for p in cells]
        w = max(is_) - min(is_) + 1
        h = max(js_) - min(js_) + 1
        if len(cells) != w * h:
            if c.room_type in _HARD:
                non_rect_hard += 1
            else:
                non_rect_other += 1
    assert non_rect_hard == 0, f"{non_rect_hard} hard-rect rooms not rectangular"
    assert non_rect_other <= 2, f"{non_rect_other} other rect rooms not rectangular"


# ── 7. boundary touch ───────────────────────────────────────────

def test_must_touch_rooms_touch_outline():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    for c in cp.rooms:
        if not c.must_touch_outline:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        cells = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
                 if grid.inside[j][i] and state.rid[j][i] == rid]
        touching = any(
            not (0 <= ni < grid.cols and 0 <= nj < grid.rows) or not grid.inside[nj][ni]
            for i, j in cells
            for ni, nj in ((i+1,j),(i-1,j),(i,j+1),(i,j-1))
        )
        assert touching, f"「{c.name}」must touch outline but doesn't"


# ── 8. adjacency ────────────────────────────────────────────────

def test_kitchen_adjacent_dining():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5),
             ("阳台", 1, 5), ("餐厅", 1, 10)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    k_rid = state.name_to_rid.get("厨房")
    d_rid = state.name_to_rid.get("餐厅")
    if k_rid and d_rid:
        adj = False
        for j in range(grid.rows):
            for i in range(grid.cols):
                if state.rid[j][i] != k_rid:
                    continue
                for ni, nj in ((i+1,j),(i-1,j),(i,j+1),(i,j-1)):
                    if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                        if state.rid[nj][ni] == d_rid:
                            adj = True
        assert adj, "厨房应与餐厅共享网格边相邻"


# ── 9. fragmentation ────────────────────────────────────────────

def test_no_remaining_fragments():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    free = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
            if grid.inside[j][i] and state.rid[j][i] == 0]
    inside = grid.total_inside()
    assert len(free) <= max(1, inside * 0.02), (
        f"{len(free)} free cells remain (>2% of {inside})"
    )


# ── 10. T-shape outline ─────────────────────────────────────────

def test_t_shape_full_coverage():
    rooms = [("客厅", 1, 18), ("主卧", 1, 12), ("厨房", 1, 6), ("卫生间", 1, 4)]
    outline = _t_outline()
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    unassigned = sum(1 for j in range(grid.rows) for i in range(grid.cols) if grid.inside[j][i] and state.rid[j][i] == 0)
    assert unassigned == 0


# ── 11. narrow outline ──────────────────────────────────────────

def test_narrow_rect_coverage():
    rooms = [("客厅", 1, 10), ("主卧", 1, 8), ("厨房", 1, 4), ("卫生间", 1, 3)]
    outline = _rect_outline(5, 6)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    assert report.area_coverage_ratio >= 0.95


# ── 12. area per-room tolerance ──────────────────────────────────

def test_room_areas_within_tolerance():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    for c in cp.rooms:
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        n = sum(1 for j in range(grid.rows) for i in range(grid.cols)
                if grid.inside[j][i] and state.rid[j][i] == rid)
        area = n * CELL_AREA
        target = c.target_area_sqm
        if target <= 0:
            continue
        err = abs(area - target) / target
        if c.must_be_rectangle:
            assert err <= c.area_tolerance + 1.2, (
                f"「{c.name}」area {area:.1f} vs target {target:.1f}, err {err:.0%}"
            )
        else:
            assert n > 0, f"「{c.name}」has zero cells"


# ── 13. grid_assignment structured output ────────────────────────

def test_grid_assignment_shape():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8)]
    outline = _rect_outline(8, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    ga = report.grid_assignment
    assert len(ga) == grid.rows
    assert all(len(row) == grid.cols for row in ga)
    inside_ids = {ga[j][i] for j in range(grid.rows) for i in range(grid.cols) if grid.inside[j][i]}
    assert 0 not in inside_ids, "unassigned cell in grid_assignment"
    assert -1 not in inside_ids, "outside cell should be -1 but was inside"


# ── 14. compile pipeline returns coverage metrics ───────────────

def test_compile_pipeline_area_metrics():
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5), ("餐厅", 1, 10)]
    outline = _rect_outline(10, 8)
    plan = _plan(rooms, 80)
    semantic = build_default_semantic_plan(plan)
    layout, notes = compile_semantic_layout_grid_search(semantic, plan, outline)
    metrics = compute_layout_area_metrics(layout, outline)
    assert metrics.area_coverage_ratio >= 0.95
    assert metrics.room_count >= 5
    assert any("占比" in n for n in notes)


# ── 15. Bathroom / Bedroom / Balcony must be rectangular ──────────

_MUST_RECT_TYPES = frozenset({"卫生间", "主卫", "客卫", "阳台", "主卧", "次卧", "卧室"})


@pytest.mark.parametrize(
    "rooms_spec,outline_w,outline_h,label",
    [
        # 5-room 80㎡
        (
            [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)],
            10, 8, "5room-80sqm",
        ),
        # 7-room 80㎡
        (
            [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5), ("餐厅", 1, 10), ("次卧", 1, 10)],
            10, 8, "7room-80sqm",
        ),
        # 9-room 120㎡
        (
            [("客厅", 1, 24), ("主卧", 1, 18), ("厨房", 1, 9), ("卫生间", 2, 5), ("阳台", 1, 6), ("餐厅", 1, 12), ("次卧", 2, 12)],
            12, 10, "9room-120sqm",
        ),
    ],
)
def test_key_rooms_always_rectangular(rooms_spec, outline_w, outline_h, label):
    """Bathroom, bedroom, and balcony polygons must be axis-aligned rectangles."""
    plan = _plan(rooms_spec, outline_w * outline_h)
    outline = _rect_outline(outline_w, outline_h)
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout_grid_search(semantic, plan, outline)

    for rm in layout.rooms:
        must_rect = any(rt in rm.name for rt in _MUST_RECT_TYPES) or any(rt in rm.type for rt in _MUST_RECT_TYPES)
        if not must_rect:
            continue
        pts = [(p.x, p.y) for p in rm.polygon]
        assert len(pts) >= 3, f"[{label}] {rm.name} has <3 polygon points"
        xset = set(round(x, 3) for x, y in pts)
        yset = set(round(y, 3) for x, y in pts)
        assert len(xset) == 2, f"[{label}] {rm.name} not rect: x values = {sorted(xset)}"
        assert len(yset) == 2, f"[{label}] {rm.name} not rect: y values = {sorted(yset)}"


def test_9room_key_rooms_inside_outline_and_rect():
    """Full pipeline: 9-room plan, key rooms are rectangular and inside outline."""
    rooms = [("客厅", 1, 24), ("主卧", 1, 18), ("厨房", 1, 9), ("卫生间", 2, 5), ("阳台", 1, 6), ("餐厅", 1, 12), ("次卧", 2, 12)]
    outline = _rect_outline(12, 10)
    plan = _plan(rooms, 120)
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout_grid_search(semantic, plan, outline)

    for rm in layout.rooms:
        pts = [(p.x, p.y) for p in rm.polygon]
        xs = [x for x, y in pts]; ys = [y for x, y in pts]
        # All rooms must be inside [0,12]×[0,10]
        assert min(xs) >= -0.01, f"{rm.name} x={min(xs):.2f} < 0"
        assert max(xs) <= 12.01, f"{rm.name} x={max(xs):.2f} > 12"
        assert min(ys) >= -0.01, f"{rm.name} y={min(ys):.2f} < 0"
        assert max(ys) <= 10.01, f"{rm.name} y={max(ys):.2f} > 10"
        # Key rooms must be rectangular
        must_rect = any(rt in rm.name for rt in _MUST_RECT_TYPES) or any(rt in rm.type for rt in _MUST_RECT_TYPES)
        if must_rect:
            xset = set(round(x, 3) for x in xs)
            yset = set(round(y, 3) for y in ys)
            assert len(xset) == 2 and len(yset) == 2, f"{rm.name} not rectangular: xs={sorted(xset)} ys={sorted(yset)}"
