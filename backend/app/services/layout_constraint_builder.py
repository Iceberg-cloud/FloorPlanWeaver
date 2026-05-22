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
from app.services.semantic_validator import reconcile_semantic_with_program

# User-specified placement priority (lower = earlier)
_PRIORITY_ORDER: list[str] = [
    "阳台",
    "卫生间", "主卫", "客卫", "洗手间", "厕所",
    "主卧",
    "次卧", "卧室", "儿童房",
    "厨房",
    "书房",
    "餐厅",
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
        return dict(must_touch_outline=False, must_be_rectangle=True, allow_non_rect=True, area_tolerance=0.3)
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

    rooms: list[RoomPlacementConstraint] = []
    for entry in list(entries.fixed) + list(entries.flexible):
        rt = entry.room_type or entry.name
        rules = _room_rules(rt)
        zone = llm.room_zone.get(rt, entry.zone if entry.zone != "flexible" else "center")
        pos_hint = entry.corner_hint or hint_map.get(rt, zone)
        hx, hy = xy_map.get(rt, (0.5, 0.5))
        rooms.append(
            RoomPlacementConstraint(
                name=entry.name,
                room_type=rt,
                target_area_sqm=max(3.0, entry.target_area),
                area_tolerance=rules["area_tolerance"],
                zone_preference=zone,
                preferred_orientation=orient_map.get(rt, zone if zone in ("south", "north", "east", "west") else ""),
                preferred_position_hint=pos_hint,
                position_hint_x=hx,
                position_hint_y=hy,
                must_touch_outline=rules["must_touch_outline"],
                must_be_rectangle=rules["must_be_rectangle"],
                allow_non_rect=rules["allow_non_rect"],
                priority=_priority_index(rt),
                near_rooms=near_map.get(rt, entry.near_rooms or []),
                avoid_rooms=avoid_map.get(rt, entry.avoid_rooms or []),
                adjacency_required=adj_req.get(entry.name, adj_req.get(rt, [])),
                adjacency_preferred=adj_pref.get(entry.name, adj_pref.get(rt, [])),
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
