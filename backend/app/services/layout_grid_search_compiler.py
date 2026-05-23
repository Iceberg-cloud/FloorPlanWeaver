"""Compile layout via constraint parse + grid beam search (Method A)."""

from __future__ import annotations

from app.schemas.layout import LayoutDraft, LayoutRoom, Point2D, SiteOutline
from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import SemanticLayoutPlan
from app.services.layout_constraint_builder import build_constraint_plan
from app.services.layout_compiler import POLYGON_ROOM_TYPES, _entry_room_type
from app.services.layout_geometry import bbox_of_polygon
from app.services.layout_grid import CELL_AREA, GridMap
from app.services.layout_grid_search import run_grid_search_layout
from app.services.layout_metrics import compute_layout_area_metrics


def compile_semantic_layout_grid_search(
    semantic: SemanticLayoutPlan,
    plan: PlannerFinalPlan,
    outline: SiteOutline,
) -> tuple[LayoutDraft, list[str]]:
    """Returns layout draft and diagnostic notes."""
    notes: list[str] = []
    if not outline.vertices:
        return LayoutDraft(compile_method="grid_search"), notes

    poly = [(v.x, v.y) for v in outline.vertices]
    min_x, min_y, max_x, max_y = bbox_of_polygon(poly)
    bbox_w, bbox_h = max_x - min_x, max_y - min_y
    if bbox_w < 0.5 or bbox_h < 0.5:
        return LayoutDraft(
            outline_vertices=outline.vertices,
            entrance_edge=outline.entrance_edge,
            compile_method="grid_search",
        ), notes

    constraint_plan = build_constraint_plan(plan, semantic, outline)
    notes.append("布局管线：LLM 语义约束 → 网格 beam 搜索 → 规则校验。")

    state, grid, report = run_grid_search_layout(constraint_plan, outline)
    notes.append(f"搜索评分：{report.total_score:.1f}")
    notes.append(
        f"网格占比 {report.area_coverage_ratio:.1%} "
        f"（{report.planned_area_sqm:.1f}/{report.outline_area_sqm:.1f}㎡）"
    )
    if report.repair_log:
        notes.append("修复：" + "；".join(report.repair_log[:3]))
    if report.explanation:
        notes.append(report.explanation)
    if report.violations:
        notes.extend([f"校验：{v}" for v in report.violations[:6]])
    else:
        notes.append("校验：全部硬约束通过。")

    if state is None:
        notes.append("网格搜索完全失败，无法生成布局。")
        return LayoutDraft(
            outline_vertices=outline.vertices,
            entrance_edge=outline.entrance_edge,
            compile_method="grid_search",
        ), notes

    rooms = _export_rooms_from_state(grid, state, constraint_plan.rooms, outline.vertices)
    draft = LayoutDraft(
        canvas={"width": bbox_w, "height": bbox_h},
        outline_vertices=outline.vertices,
        entrance_edge=outline.entrance_edge,
        rooms=rooms,
        doors=[],
        windows=[],
        compile_method="grid_search",
    )
    metrics = compute_layout_area_metrics(draft, outline)
    notes.append(metrics.summary_line())
    notes.append(
        f"网格搜索占比 {report.area_coverage_ratio:.1%}，"
        f"多边形汇总占比 {metrics.area_coverage_ratio:.1%}"
    )
    return draft, notes


def _export_rooms_from_state(
    grid: GridMap,
    state,
    constraints,
    outline_vertices,
) -> list[LayoutRoom]:
    rooms: list[LayoutRoom] = []
    idx = 0
    grid.rid = state.rid  # sync once

    # Rect types: bathroom, bedroom, balcony must always be rectangular.
    _FORCE_RECT_TYPES = frozenset({
        "卫生间", "主卫", "客卫", "洗手间", "厕所",
        "主卧", "次卧", "卧室", "儿童房",
        "阳台",
    })
    # Kitchen can be rect or L-shape
    _KITCHEN_TYPE = "厨房"

    for c in constraints:
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        n = sum(
            1 for j in range(grid.rows) for i in range(grid.cols)
            if grid.inside[j][i] and state.rid[j][i] == rid
        )
        if n < 1:
            continue
        idx += 1
        rt = c.room_type
        is_poly_type = rt in POLYGON_ROOM_TYPES
        must_be_rect = c.must_be_rectangle or rt in _FORCE_RECT_TYPES
        is_hard_rect = rt in _FORCE_RECT_TYPES

        if is_poly_type:
            pts, shape_kind = grid.export_room_polygon(rid, prefer_rectangle=False)
            if len(pts) >= 3:
                shape_kind = "polygon"
        else:
            pts, shape_kind = grid.export_room_polygon(
                rid,
                prefer_rectangle=must_be_rect,
            )

        # Hard rect types: force 4-point bbox even if grid is not solid rect
        if is_hard_rect and (len(pts) != 4 or shape_kind != "rect"):
            bbox_pts = grid.cells_to_bbox_polygon(rid)
            if len(bbox_pts) == 4:
                pts = bbox_pts
                shape_kind = "rect"
        if len(pts) < 3:
            continue
        area = round(n * CELL_AREA, 1)
        rooms.append(
            LayoutRoom(
                id=f"r{idx}",
                name=c.name,
                type=rt,
                polygon=[Point2D(x=x, y=y) for x, y in pts],
                area_sqm=area,
                adjacent_to=[],
                shape_kind=shape_kind,
            )
        )
    return rooms
