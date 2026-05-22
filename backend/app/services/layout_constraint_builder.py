"""Build structured constraints from planner plan + semantic LLM (no coordinates)."""

from __future__ import annotations

from app.schemas.layout import SiteOutline
from app.schemas.layout_constraints import LayoutConstraintPlan, RoomPlacementConstraint
from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import SemanticLayoutPlan
from app.services.layout_compiler import (
    _build_entries_from_llm,
    _extract_llm_constraints,
    _unique_room_label,
)
from app.services.layout_geometry import bbox_of_polygon
from app.services.room_layout_conventions import (
    merge_avoid_lists,
    merge_near_lists,
    min_target_area,
    prefer_edge_for,
    typical_aspect_bounds,
    zone_for,
)
from app.services.semantic_validator import reconcile_semantic_with_program

# User-specified placement priority (lower = earlier)
_PRIORITY_ORDER: list[str] = [
    "阳台",
    "卫生间", "主卫", "客卫", "洗手间", "厕所",
    "主卧",
    "次卧", "卧室", "儿童房",
    "餐厅",
    "厨房",
    "书房",
    "客厅", "起居室", "客餐厅",
]


def _priority_index(room_type: str) -> int:
    rt = (room_type or "").strip()
    for i, key in enumerate(_PRIORITY_ORDER):
        if rt == key or rt.startswith(key):
            return i
    return 80


def _room_rules(room_type: str) -> dict:
    rt = room_type or ""
    if rt in ("阳台",):
        return dict(must_touch_outline=True, must_be_rectangle=True, allow_non_rect=False, area_tolerance=0.3)
    if rt in ("卫生间", "主卫", "客卫", "洗手间", "厕所"):
        return dict(must_touch_outline=True, must_be_rectangle=True, allow_non_rect=False, area_tolerance=0.25)
    if rt in ("主卧", "次卧", "卧室", "儿童房"):
        return dict(must_touch_outline=True, must_be_rectangle=True, allow_non_rect=False, area_tolerance=0.25)
    if rt == "厨房":
        return dict(must_touch_outline=True, must_be_rectangle=True, allow_non_rect=True, area_tolerance=0.25)
    if rt == "书房":
        return dict(must_touch_outline=False, must_be_rectangle=True, allow_non_rect=True, area_tolerance=0.3)
    if rt in ("餐厅", "客厅", "起居室", "客餐厅"):
        return dict(must_touch_outline=False, must_be_rectangle=False, allow_non_rect=True, area_tolerance=0.35)
    return dict(must_touch_outline=False, must_be_rectangle=False, allow_non_rect=True, area_tolerance=0.3)


def build_constraint_plan(
    plan: PlannerFinalPlan,
    semantic: SemanticLayoutPlan,
    outline: SiteOutline,
) -> LayoutConstraintPlan:
    semantic = reconcile_semantic_with_program(plan, semantic)
    poly = [(v.x, v.y) for v in outline.vertices]
    min_x, min_y, max_x, max_y = bbox_of_polygon(poly)
    llm = _extract_llm_constraints(semantic, outline, min_x, min_y, max_x, max_y)
    entries = _build_entries_from_llm(plan, semantic, llm)

    near_map: dict[str, list[str]] = {}
    avoid_map: dict[str, list[str]] = {}
    hint_map: dict[str, str] = {}
    xy_map: dict[str, tuple[float, float]] = {}
    orient_map: dict[str, str] = {}
    for p in semantic.placements:
        near_map[p.room_type] = list(p.near or [])
        avoid_map[p.room_type] = list(p.avoid or [])
        hint_map[p.room_type] = (p.prefer_edge or p.zone or "").strip()
        xy_map[p.room_type] = (float(p.center_x), float(p.center_y))
        z = (p.zone or "").lower()
        if z in ("south", "north", "east", "west", "center"):
            orient_map[p.room_type] = z

    adj_req: dict[str, list[str]] = {}
    adj_pref: dict[str, list[str]] = {}
    for a, b in llm.adjacency_must:
        adj_req.setdefault(a, []).append(b)
        adj_req.setdefault(b, []).append(a)
    for a, b in llm.adjacency_prefer:
        adj_pref.setdefault(a, []).append(b)
        adj_pref.setdefault(b, []).append(a)
    for intent in semantic.adjacency_intent:
        if intent.strength == "must":
            adj_req.setdefault(intent.a, []).append(intent.b)
            adj_req.setdefault(intent.b, []).append(intent.a)
        elif intent.strength == "prefer":
            adj_pref.setdefault(intent.a, []).append(intent.b)
            adj_pref.setdefault(intent.b, []).append(intent.a)

    for edge in plan.adjacency_graph:
        src, tgt = edge.source, edge.target
        if not src or not tgt:
            continue
        if edge.relation in ("required", "must"):
            if tgt not in adj_req.get(src, []):
                adj_req.setdefault(src, []).append(tgt)
            if src not in adj_req.get(tgt, []):
                adj_req.setdefault(tgt, []).append(src)
        elif edge.relation in ("preferred", "prefer"):
            if tgt not in adj_pref.get(src, []):
                adj_pref.setdefault(src, []).append(tgt)
            if src not in adj_pref.get(tgt, []):
                adj_pref.setdefault(tgt, []).append(src)

    rooms: list[RoomPlacementConstraint] = []
    for entry in list(entries.fixed) + list(entries.flexible):
        rt = entry.room_type or entry.name
        rules = _room_rules(rt)
        zone = zone_for(
            rt,
            llm.room_zone.get(rt, entry.zone if entry.zone != "flexible" else "center"),
        )
        pos_hint = entry.corner_hint or hint_map.get(rt, zone)
        edge = prefer_edge_for(rt, hint_map.get(rt, "") or orient_map.get(rt, ""))
        target_sqm = max(min_target_area(rt), float(entry.target_area or 8))
        asp_min, asp_max = typical_aspect_bounds(rt)
        near = merge_near_lists(
            list(near_map.get(rt, entry.near_rooms or [])),
            rt,
        )
        if rt == "厨房" and "餐厅" not in near:
            near.append("餐厅")
        if rt == "餐厅" and "厨房" not in near:
            near.append("厨房")
        avoid = merge_avoid_lists(
            list(avoid_map.get(rt, entry.avoid_rooms or [])),
            rt,
        )
        adj_pref_list = list(adj_pref.get(entry.name, adj_pref.get(rt, [])))
        for other in merge_near_lists([], rt):
            if other not in adj_pref_list:
                adj_pref_list.append(other)
        hx, hy = xy_map.get(rt, (0.5, 0.5))
        rooms.append(
            RoomPlacementConstraint(
                name=entry.name,
                room_type=rt,
                target_area_sqm=target_sqm,
                area_tolerance=rules["area_tolerance"],
                zone_preference=zone,
                preferred_orientation=edge or orient_map.get(
                    rt, zone if zone in ("south", "north", "east", "west") else "",
                ),
                preferred_position_hint=pos_hint,
                position_hint_x=hx,
                position_hint_y=hy,
                must_touch_outline=rules["must_touch_outline"],
                must_be_rectangle=rules["must_be_rectangle"],
                aspect_min=asp_min,
                aspect_max=asp_max,
                allow_non_rect=rules["allow_non_rect"],
                priority=_priority_index(rt),
                near_rooms=near,
                avoid_rooms=avoid,
                adjacency_required=adj_req.get(entry.name, adj_req.get(rt, [])),
                adjacency_preferred=adj_pref_list,
                index=entry.index,
            )
        )

    rooms.sort(key=lambda r: (r.priority, r.name))

    return LayoutConstraintPlan(
        entrance_side=llm.entrance_side,
        public_side=semantic.public_side or "south",
        rooms=rooms,
        adjacency_must=list(llm.adjacency_must),
        adjacency_prefer=list(llm.adjacency_prefer),
        adjacency_avoid=getattr(llm, "adjacency_avoid", []) or [],
    )


def constraint_counts_match_program(
    constraint_plan: LayoutConstraintPlan,
    plan: PlannerFinalPlan,
) -> bool:
    """True when each space_program room type/count matches constraint rooms."""
    from collections import Counter

    prog: Counter[str] = Counter()
    for item in plan.space_program:
        prog[item.room_type] += max(1, item.count)
    cons: Counter[str] = Counter()
    for r in constraint_plan.rooms:
        cons[r.room_type] += 1
    return prog == cons


def expand_program_labels(plan: PlannerFinalPlan) -> list[tuple[str, str, float, int]]:
    """name, room_type, area, index for each instance."""
    out: list[tuple[str, str, float, int]] = []
    for item in plan.space_program:
        count = max(1, item.count)
        area = float(item.target_area_sqm or 12)
        for idx in range(1, count + 1):
            name = _unique_room_label(item.room_type, idx, count)
            out.append((name, item.room_type, area, idx))
    return out
