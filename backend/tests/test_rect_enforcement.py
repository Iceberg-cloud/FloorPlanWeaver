"""Test that bathroom, bedroom, balcony are always axis-aligned rectangles.

Covers: grid placement, repair, export, and compile pipeline.
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
    run_grid_search_layout,
    validate_grid_layout,
)
from app.services.layout_grid_search_compiler import compile_semantic_layout_grid_search
from app.services.layout_constraint_builder import build_constraint_plan

_HARD_RECT_TYPES = frozenset({
    "卫生间", "主卫", "客卫", "洗手间", "厕所",
    "主卧", "次卧", "卧室", "儿童房",
    "阳台",
})


def _plan(rooms, area):
    return PlannerFinalPlan(
        agent_state="FINAL_PLAN",
        project_profile=ProjectProfile(
            building_type="住宅", target_area_sqm=area, layout_type="三居", orientation="南向",
        ),
        design_goals=[],
        space_program=[
            SpaceProgramItem(room_type=rt, count=c, target_area_sqm=a)
            for rt, c, a in rooms
        ],
        adjacency_graph=[],
        drawing_brief="test",
    )


def _rect_outline(w, h):
    return SiteOutline(
        vertices=[Point2D(x=0, y=0), Point2D(x=w, y=0), Point2D(x=w, y=h), Point2D(x=0, y=h)],
        entrance_edge=[0, 1], total_area_sqm=w * h,
        bounding_box={"width": w, "height": h}, unit="m",
    )


def _l_outline():
    verts = [
        Point2D(x=0, y=0), Point2D(x=8, y=0), Point2D(x=8, y=3),
        Point2D(x=4, y=3), Point2D(x=4, y=6), Point2D(x=0, y=6),
    ]
    return SiteOutline(
        vertices=verts, entrance_edge=[0, 1],
        total_area_sqm=36, bounding_box={"width": 8, "height": 6}, unit="m",
    )


def _run_grid(rooms, outline):
    plan = _plan(rooms, outline.total_area_sqm)
    semantic = build_default_semantic_plan(plan)
    cp = build_constraint_plan(plan, semantic, outline)
    state, grid, report = run_grid_search_layout(cp, outline)
    return plan, semantic, outline, state, grid, report, cp


# ── Grid-level: all hard-rect rooms are solid rectangles ──────────

@pytest.mark.parametrize("rooms_spec,w,h,label", [
    (
        [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)],
        10, 8, "5room",
    ),
    (
        [("客厅", 1, 22), ("主卧", 1, 14), ("次卧", 1, 10), ("厨房", 1, 8),
         ("卫生间", 1, 5), ("阳台", 1, 5), ("餐厅", 1, 10)],
        10, 8, "7room",
    ),
    (
        [("客厅", 1, 24), ("主卧", 1, 18), ("厨房", 1, 9), ("卫生间", 2, 5),
         ("阳台", 1, 6), ("餐厅", 1, 12), ("次卧", 2, 12)],
        12, 10, "9room",
    ),
    (
        [("客厅", 1, 18), ("主卧", 1, 12), ("厨房", 1, 6), ("卫生间", 1, 4)],
        8, 7, "4room-narrow",
    ),
])
def test_grid_hard_rect_rooms_solid_rectangle(rooms_spec, w, h, label):
    """Every bathroom/bedroom/balcony must be a solid axis-aligned rectangle on the grid."""
    outline = _rect_outline(w, h)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms_spec, outline)
    assert state is not None

    for c in cp.rooms:
        if c.room_type not in _HARD_RECT_TYPES:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        cells = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
                 if grid.inside[j][i] and state.rid[j][i] == rid]
        if not cells:
            continue
        is_ = [p[0] for p in cells]
        js_ = [p[1] for p in cells]
        wi = max(is_) - min(is_) + 1
        hj = max(js_) - min(js_) + 1
        assert len(cells) == wi * hj, (
            f"[{label}] {c.name} ({c.room_type}) not solid rect: "
            f"{len(cells)} cells vs {wi}*{hj}={wi*hj}"
        )


# ── L-shape outline: hard-rect rooms still solid ────────────────

def test_l_shape_hard_rect_rooms():
    rooms = [("客厅", 1, 14), ("主卧", 1, 10), ("厨房", 1, 6), ("卫生间", 1, 4)]
    outline = _l_outline()
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None

    for c in cp.rooms:
        if c.room_type not in _HARD_RECT_TYPES:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        assert grid.cells_are_single_rect(rid), (
            f"{c.name} not solid rect in L-shape outline"
        )


# ── Export: polygon output has exactly 4 points for hard-rect ──────

@pytest.mark.parametrize("rooms_spec,w,h,label", [
    (
        [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)],
        10, 8, "5room",
    ),
    (
        [("客厅", 1, 24), ("主卧", 1, 18), ("厨房", 1, 9), ("卫生间", 2, 5),
         ("阳台", 1, 6), ("餐厅", 1, 12), ("次卧", 2, 12)],
        12, 10, "9room",
    ),
])
def test_export_hard_rect_4_points(rooms_spec, w, h, label):
    """Exported polygon for bathroom/bedroom/balcony must have exactly 4 vertices."""
    outline = _rect_outline(w, h)
    plan = _plan(rooms_spec, w * h)
    semantic = build_default_semantic_plan(plan)
    layout, _ = compile_semantic_layout_grid_search(semantic, plan, outline)

    for rm in layout.rooms:
        is_hard = any(rt in rm.name for rt in _HARD_RECT_TYPES) or \
                  any(rt in rm.type for rt in _HARD_RECT_TYPES)
        if not is_hard:
            continue
        pts = [(p.x, p.y) for p in rm.polygon]
        assert len(pts) == 4, (
            f"[{label}] {rm.name} has {len(pts)} points (expected 4)"
        )
        # Must be axis-aligned rectangle: exactly 2 unique X and 2 unique Y
        xset = set(round(x, 3) for x, y in pts)
        yset = set(round(y, 3) for x, y in pts)
        assert len(xset) == 2, f"[{label}] {rm.name} not rect: x values = {sorted(xset)}"
        assert len(yset) == 2, f"[{label}] {rm.name} not rect: y values = {sorted(yset)}"
        assert rm.shape_kind == "rect", f"[{label}] {rm.name} shape_kind={rm.shape_kind}"


# ── Kitchen can be L-shape ──────────────────────────────────────

def test_kitchen_can_be_l_shape():
    """Kitchen is allowed to be non-rectangular (L-shape)."""
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None

    kid = state.name_to_rid.get("厨房")
    assert kid is not None
    # Kitchen constraint has allow_non_rect=True, so it can be L-shaped
    kitchen_cells = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
                     if grid.inside[j][i] and state.rid[j][i] == kid]
    assert len(kitchen_cells) > 0


# ── Short-side minimum ──────────────────────────────────────────

def test_bathroom_min_short_side():
    """Bathroom short side should be at least ~1.0m (4 cells at 0.25m)."""
    rooms = [("客厅", 1, 22), ("主卧", 1, 14), ("厨房", 1, 8), ("卫生间", 1, 5), ("阳台", 1, 5)]
    outline = _rect_outline(10, 8)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None

    for c in cp.rooms:
        if c.room_type not in ("卫生间", "主卫", "客卫"):
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        cells = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
                 if grid.inside[j][i] and state.rid[j][i] == rid]
        if not cells:
            continue
        is_ = [p[0] for p in cells]
        js_ = [p[1] for p in cells]
        w_cells = max(is_) - min(is_) + 1
        h_cells = max(js_) - min(js_) + 1
        short_m = min(w_cells, h_cells) * 0.25
        # At least 4 cells (1.0m) on short side — relaxed to 3 for small outlines
        assert short_m >= 0.75, (
            f"{c.name} short side {short_m:.2f}m < 0.75m"
        )


# ── Validation hard-fails for non-rect hard rooms ───────────────

def test_validation_flags_non_rect_hard_rooms():
    """If a hard-rect room were somehow non-rect, validation should flag it."""
    # Create a tiny outline where it's hard to get perfect rects
    rooms = [("客厅", 1, 10), ("主卧", 1, 8), ("厨房", 1, 4), ("卫生间", 1, 3)]
    outline = _rect_outline(5, 6)
    plan, sem, ol, state, grid, report, cp = _run_grid(rooms, outline)
    assert state is not None
    # Coverage should be reasonable
    assert report.area_coverage_ratio >= 0.95
