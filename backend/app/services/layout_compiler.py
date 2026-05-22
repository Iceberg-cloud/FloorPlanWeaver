"""Compile SemanticLayoutPlan → LayoutDraft using LLM-driven greedy packing.

Phase 0: Extract constraints from LLM semantic plan.
Phase 1: Place fixed (rectangular) rooms against outline edges.
Phase 2: Assign remaining polygon to flexible rooms (living/dining).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.schemas.layout import LayoutDraft, LayoutRoom, Point2D, SiteOutline
from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import RoomPlacement, SemanticLayoutPlan
from app.services.layout_geometry import (
    bbox_of_polygon,
    point_in_polygon,
    polygon_area,
    rect_area,
    rect_to_polygon,
    shrink_rect_into_polygon,
)
from app.services.rule_layout_engine import DEFAULT_AREAS

GAP = 0.10
_EPS = 0.05

_SERVICE_TYPES = frozenset({"卫生间", "主卫", "客卫", "洗手间"})
_KITCHEN_TYPES = frozenset({"厨房"})
_BALCONY_TYPES = frozenset({"阳台"})
_BEDROOM_TYPES = frozenset({"主卧", "次卧", "书房", "卧室", "儿童房"})
_FLEXIBLE_TYPES = frozenset({"客厅", "餐厅", "起居室", "客餐厅"})
POLYGON_ROOM_TYPES = frozenset({"客厅", "餐厅", "起居室", "客餐厅", "书房"})

_CORNER_POS = {"BL": (0, 0), "BR": (1, 0), "TL": (0, 1), "TR": (1, 1)}


def _unique_room_label(room_type: str, index: int, total: int) -> str:
    if total <= 1:
        return room_type
    return f"{room_type}{index}"


def _entry_room_type(entry) -> str:
    return getattr(entry, 'room_type', '') or entry.name


@dataclass
class _Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    @property
    def w(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def h(self) -> float:
        return max(0.0, self.y1 - self.y0)


@dataclass
class _RoomEntry:
    name: str
    target_area: float
    zone: str
    room_type: str = ""
    corner_hint: str = ""
    prefer_edge: str = ""
    near_rooms: list[str] = field(default_factory=list)
    avoid_rooms: list[str] = field(default_factory=list)
    cluster: str = "other"
    index: int = 1
    hint_center_x: float | None = None
    hint_center_y: float | None = None
    hint_width_ratio: float | None = None
    hint_height_ratio: float | None = None


@dataclass
class LLMConstraints:
    entrance_side: str
    entrance_mid: tuple[float, float]
    public_side: str
    entrance_room: str
    room_zone: dict[str, str]
    room_edge: dict[str, str]
    room_near: dict[str, list[str]]
    room_avoid: dict[str, list[str]]
    room_cluster: dict[str, str]
    room_size: dict[str, str]
    adjacency_must: list[tuple[str, str]]
    adjacency_prefer: list[tuple[str, str]]
    adjacency_avoid: list[tuple[str, str]]
    bands: list[list[str]]


@dataclass
class _EntriesResult:
    fixed: list[_RoomEntry]
    flexible: list[_RoomEntry]


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def compile_semantic_layout(
    semantic: SemanticLayoutPlan,
    plan: PlannerFinalPlan,
    outline: SiteOutline,
) -> tuple[LayoutDraft, list[str]]:
    from app.core.config import settings

    if settings.layout_use_grid_compiler:
        from app.services.layout_grid_compiler import compile_semantic_layout_grid

        return compile_semantic_layout_grid(semantic, plan, outline)

    if not outline.vertices:
        return LayoutDraft(), []

    poly = [(v.x, v.y) for v in outline.vertices]
    min_x, min_y, max_x, max_y = bbox_of_polygon(poly)
    bbox_w, bbox_h = max_x - min_x, max_y - min_y
    if bbox_w < 0.5 or bbox_h < 0.5:
        return LayoutDraft(outline_vertices=outline.vertices, entrance_edge=outline.entrance_edge), []

    constraints = _extract_llm_constraints(semantic, outline, min_x, min_y, max_x, max_y)
    entries = _build_entries_from_llm(plan, semantic, constraints)

    placed_rects = _place_rects_against_outline(entries.fixed, poly, constraints)

    remaining = _compute_remaining_polygon(poly, placed_rects)
    flex_polys = _assign_remaining_to_flex(
        remaining,
        entries.flexible,
        poly,
        constraints,
    )

    rooms = _make_rooms(placed_rects, flex_polys, poly, outline)

    return LayoutDraft(
        canvas={"width": bbox_w, "height": bbox_h},
        outline_vertices=outline.vertices,
        entrance_edge=outline.entrance_edge,
        rooms=rooms,
        doors=[],
        windows=[],
    ), ["legacy 矢量编译"]


# ---------------------------------------------------------------------------
# LLM constraint extraction
# ---------------------------------------------------------------------------
def _extract_llm_constraints(
    semantic: SemanticLayoutPlan,
    outline: SiteOutline,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> LLMConstraints:
    entrance_side = _get_entrance_side(outline, min_x, min_y, max_x, max_y)
    entrance_mid = _entrance_midpoint(outline)

    room_zone: dict[str, str] = {}
    room_edge: dict[str, str] = {}
    room_near: dict[str, list[str]] = {}
    room_avoid: dict[str, list[str]] = {}
    room_cluster: dict[str, str] = {}
    room_size: dict[str, str] = {}

    for p in semantic.placements:
        room_zone[p.room_type] = p.zone
        if p.prefer_edge:
            room_edge[p.room_type] = p.prefer_edge
        if p.near:
            room_near[p.room_type] = list(p.near)
        if p.avoid:
            room_avoid[p.room_type] = list(p.avoid)
        room_cluster[p.room_type] = p.cluster
        room_size[p.room_type] = p.size

    adjacency_must: list[tuple[str, str]] = []
    adjacency_prefer: list[tuple[str, str]] = []
    adjacency_avoid: list[tuple[str, str]] = []
    for adj in semantic.adjacency_intent:
        pair = (adj.a, adj.b)
        if adj.strength == "must":
            adjacency_must.append(pair)
        elif adj.strength == "avoid":
            adjacency_avoid.append(pair)
        else:
            adjacency_prefer.append(pair)

    bands = [list(b.order) for b in semantic.bands if b.order]

    return LLMConstraints(
        entrance_side=entrance_side,
        entrance_mid=entrance_mid,
        public_side=semantic.public_side or "south",
        entrance_room=semantic.entrance_room or "",
        room_zone=room_zone,
        room_edge=room_edge,
        room_near=room_near,
        room_avoid=room_avoid,
        room_cluster=room_cluster,
        room_size=room_size,
        adjacency_must=adjacency_must,
        adjacency_prefer=adjacency_prefer,
        adjacency_avoid=adjacency_avoid,
        bands=bands,
    )


def _entrance_midpoint(outline: SiteOutline) -> tuple[float, float]:
    if len(outline.entrance_edge) < 2 or len(outline.vertices) < 2:
        return (0.0, 0.0)
    ei, ej = outline.entrance_edge[0], outline.entrance_edge[1]
    if ei >= len(outline.vertices) or ej >= len(outline.vertices):
        return (0.0, 0.0)
    v1, v2 = outline.vertices[ei], outline.vertices[ej]
    return ((v1.x + v2.x) / 2, (v1.y + v2.y) / 2)


# ---------------------------------------------------------------------------
# Build room entries from LLM + plan
# ---------------------------------------------------------------------------
def _lookup_placement(
    semantic: SemanticLayoutPlan,
    room_type: str,
    index: int,
) -> RoomPlacement | None:
    matches = [p for p in semantic.placements if p.room_type == room_type]
    if not matches:
        return None
    for p in matches:
        if p.index == index:
            return p
    if index <= len(matches):
        return matches[index - 1]
    return matches[0]


def _build_entries_from_llm(
    plan: PlannerFinalPlan,
    semantic: SemanticLayoutPlan,
    constraints: LLMConstraints,
) -> _EntriesResult:
    raw: list[_RoomEntry] = []
    type_counters: dict[str, int] = {}

    for item in plan.space_program:
        target = float(item.target_area_sqm or DEFAULT_AREAS.get(item.room_type, 8.0))
        count = max(1, item.count)
        for _ in range(count):
            type_counters[item.room_type] = type_counters.get(item.room_type, 0) + 1
            idx = type_counters[item.room_type]
            placement = _lookup_placement(semantic, item.room_type, idx)

            llm_zone = constraints.room_zone.get(item.room_type, "")
            if placement:
                llm_zone = placement.zone or llm_zone

            zone = _map_llm_zone_to_placement_zone(
                llm_zone, item.room_type, constraints.entrance_side,
            )
            prefer_edge = constraints.room_edge.get(item.room_type, "")
            if placement and placement.prefer_edge:
                prefer_edge = placement.prefer_edge

            near = list(constraints.room_near.get(item.room_type, []))
            avoid = list(constraints.room_avoid.get(item.room_type, []))
            if placement:
                near = list(placement.near) or near
                avoid = list(placement.avoid) or avoid

            cluster = constraints.room_cluster.get(item.room_type, "other")
            if placement:
                cluster = placement.cluster or cluster

            hint_cx = placement.center_x if placement else None
            hint_cy = placement.center_y if placement else None
            hint_wr = placement.width_ratio if placement else None
            hint_hr = placement.height_ratio if placement else None

            raw.append(
                _RoomEntry(
                    name=_unique_room_label(item.room_type, idx, count),
                    target_area=target,
                    zone=zone,
                    room_type=item.room_type,
                    prefer_edge=prefer_edge,
                    near_rooms=near,
                    avoid_rooms=avoid,
                    cluster=cluster,
                    index=idx,
                    hint_center_x=hint_cx,
                    hint_center_y=hint_cy,
                    hint_width_ratio=hint_wr,
                    hint_height_ratio=hint_hr,
                )
            )

    fixed = [e for e in raw if e.zone != "flexible"]
    flex = [e for e in raw if e.zone == "flexible"]
    if not flex:
        flex = [_RoomEntry("客厅", 12.0, "flexible", cluster="public")]

    fixed = _sort_fixed_entries(fixed, constraints)
    placed_so_far: list[_RoomEntry] = []
    for entry in fixed:
        entry.corner_hint = _compute_corner_from_llm(entry, constraints, placed_so_far)
        placed_so_far.append(entry)

    fixed = _reassign_corners_for_avoidance(fixed, constraints)
    back_order, front_order = _corner_orders(constraints.entrance_side)
    _spread_zone_corners(fixed, "back", back_order)
    _spread_zone_corners(fixed, "front", front_order)
    _spread_zone_corners(fixed, "back", back_order)
    flex = _sort_flexible_entries(flex, constraints)

    return _EntriesResult(fixed=fixed, flexible=flex)


def _corner_orders(entrance_side: str) -> tuple[list[str], list[str]]:
    if entrance_side == "bottom":
        return ["BL", "BR"], ["TL", "TR"]
    if entrance_side == "top":
        return ["TL", "TR"], ["BL", "BR"]
    if entrance_side == "left":
        return ["BL", "TL"], ["BR", "TR"]
    return ["BR", "TR"], ["BL", "TL"]


def _spread_zone_corners(
    entries: list, zone: str, corners: list[str],
) -> None:
    zone_entries = [e for e in entries if e.zone == zone]
    if not zone_entries:
        return
    if len(zone_entries) == 1:
        zone_entries[0].corner_hint = corners[0]
        return
    if len(zone_entries) == 2:
        zone_entries[0].corner_hint = corners[0]
        zone_entries[1].corner_hint = corners[2] if len(corners) > 2 else corners[1]
        return
    beds = [e for e in zone_entries if getattr(e, 'name', '') in _BEDROOM_TYPES or _entry_room_type(e) in _BEDROOM_TYPES]
    if len(beds) >= 2:
        beds[0].corner_hint = corners[0]
        beds[1].corner_hint = corners[2] if len(corners) > 2 else corners[-1]
        used = {beds[0].corner_hint, beds[1].corner_hint}
        others = [e for e in zone_entries if e not in beds]
        avail = [c for c in corners if c not in used]
        for i, other in enumerate(others):
            other.corner_hint = avail[i % len(avail)] if avail else corners[i % len(corners)]
        return
    for i, entry in enumerate(zone_entries):
        entry.corner_hint = corners[i % len(corners)]


def _map_llm_zone_to_placement_zone(
    llm_zone: str,
    room_type: str,
    entrance_side: str,
) -> str:
    from app.services.layout_placement_order import is_living_dining

    if is_living_dining(room_type):
        return "flexible"
    if room_type in _FLEXIBLE_TYPES:
        return "flexible"
    if not llm_zone:
        return _fallback_zone_for_type(room_type, entrance_side)

    if llm_zone == "near_entrance":
        return "front"
    if llm_zone == "far_from_entrance":
        return "back"

    front_zones = {
        "bottom": {"south", "east", "west", "center"},
        "top": {"north", "east", "west", "center"},
        "left": {"west", "north", "south", "center"},
        "right": {"east", "north", "south", "center"},
    }
    if llm_zone in front_zones.get(entrance_side, set()):
        return "front"
    if llm_zone in ("north", "south", "east", "west"):
        return "back"
    return _fallback_zone_for_type(room_type, entrance_side)


def _fallback_zone_for_type(room_type: str, entrance_side: str) -> str:
    del entrance_side
    if room_type in _FLEXIBLE_TYPES:
        return "flexible"
    if room_type in _SERVICE_TYPES:
        return "back"
    if room_type in _KITCHEN_TYPES:
        return "front"
    if room_type in _BALCONY_TYPES:
        return "back"
    if room_type in _BEDROOM_TYPES:
        return "back"
    return "front"


def _sort_fixed_entries(
    fixed: list[_RoomEntry],
    constraints: LLMConstraints,
) -> list[_RoomEntry]:
    """Small rooms first; band order as tie-breaker."""
    band_rank = _band_order_rank(constraints.bands)

    def sort_key(e: _RoomEntry) -> tuple:
        rank = band_rank.get(e.name, 50)
        service_first = 0 if e.cluster == "service" or e.name in _SERVICE_TYPES else 1
        return (service_first, e.target_area, rank)

    return sorted(fixed, key=sort_key)


def _band_order_rank(bands: list[list[str]]) -> dict[str, int]:
    rank: dict[str, int] = {}
    pos = 0
    for band in bands:
        for name in band:
            if name not in rank:
                rank[name] = pos
                pos += 1
    return rank


def _sort_flexible_entries(
    flex: list[_RoomEntry],
    constraints: LLMConstraints,
) -> list[_RoomEntry]:
    """Living room first (largest target, near entrance)."""
    living_near_entrance = _living_must_near_entrance(constraints)

    def sort_key(e: _RoomEntry) -> tuple:
        is_living = 0 if e.name == "客厅" and living_near_entrance else 1
        size_rank = 0 if e.name == "客厅" else 1
        return (is_living, size_rank, -e.target_area)

    return sorted(flex, key=sort_key)


def _living_must_near_entrance(constraints: LLMConstraints) -> bool:
    if constraints.entrance_room and "客厅" in constraints.entrance_room:
        return True
    for a, b in constraints.adjacency_must:
        if ("客厅" in (a, b)) and ("玄关" in (a, b) or "入口" in (a, b)):
            return True
    return True


def _edge_to_corners(prefer_edge: str, entrance_side: str, zone: str) -> list[str]:
    edge = (prefer_edge or "").lower()
    mapping = {
        "south": ["BL", "BR"],
        "north": ["TL", "TR"],
        "east": ["BR", "TR"],
        "west": ["BL", "TL"],
        "bottom": ["BL", "BR"],
        "top": ["TL", "TR"],
    }
    if edge in mapping:
        return mapping[edge]

    if zone == "front":
        if entrance_side == "bottom":
            return ["BL", "BR"]
        if entrance_side == "top":
            return ["TL", "TR"]
        if entrance_side == "left":
            return ["BL", "TL"]
        return ["BR", "TR"]
    if entrance_side == "bottom":
        return ["TL", "TR"]
    if entrance_side == "top":
        return ["BL", "BR"]
    if entrance_side == "left":
        return ["BR", "TR"]
    return ["BL", "TL"]


def _compute_corner_from_llm(
    entry: _RoomEntry,
    constraints: LLMConstraints,
    placed_so_far: list[_RoomEntry],
) -> str:
    from app.services.layout_llm_hints import corner_from_normalized_center, sort_corners_by_hint

    candidates = _edge_to_corners(entry.prefer_edge, constraints.entrance_side, entry.zone)
    candidates = sort_corners_by_hint(candidates, entry.hint_center_x, entry.hint_center_y)

    if entry.avoid_rooms and placed_so_far:
        avoid_corners = [p.corner_hint for p in placed_so_far if p.name in entry.avoid_rooms]
        if avoid_corners:
            return max(
                candidates,
                key=lambda c: min(_corner_distance(c, ac) for ac in avoid_corners),
            )

    if entry.hint_center_x is not None and entry.hint_center_y is not None:
        return corner_from_normalized_center(entry.hint_center_x, entry.hint_center_y)

    return candidates[0]


def _corner_distance(c1: str, c2: str) -> float:
    p1, p2 = _CORNER_POS.get(c1, (0, 0)), _CORNER_POS.get(c2, (0, 0))
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def _reassign_corners_for_avoidance(
    fixed: list[_RoomEntry],
    constraints: LLMConstraints,
) -> list[_RoomEntry]:
    avoid_pairs: list[tuple[str, str]] = list(constraints.adjacency_avoid)
    for e in fixed:
        for avoided in e.avoid_rooms:
            avoid_pairs.append((e.name, avoided))

    diagonal = {"BL": "TR", "TR": "BL", "BR": "TL", "TL": "BR"}
    seen: set[tuple[str, str]] = set()
    for a, b in avoid_pairs:
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        ea = next((e for e in fixed if e.name == a), None)
        eb = next((e for e in fixed if e.name == b), None)
        if ea and eb and ea.corner_hint:
            opp = diagonal.get(ea.corner_hint)
            if opp:
                eb.corner_hint = opp

    if any(k in _KITCHEN_TYPES for k, _ in seen) and any(
        k in _SERVICE_TYPES for k, _ in seen
    ):
        kitchen = next((e for e in fixed if e.name in _KITCHEN_TYPES), None)
        bath = next((e for e in fixed if e.name in _SERVICE_TYPES), None)
        if kitchen and bath and kitchen.corner_hint:
            opp = diagonal.get(kitchen.corner_hint)
            if opp:
                bath.corner_hint = opp

    return fixed


# ---------------------------------------------------------------------------
# Edge placement
# ---------------------------------------------------------------------------
def _place_rects_against_outline(
    entries: list[_RoomEntry],
    poly: list[tuple[float, float]],
    constraints: LLMConstraints,
) -> list[tuple[str, _Rect]]:
    min_x, min_y, max_x, max_y = bbox_of_polygon(poly)
    placed: list[tuple[str, _Rect]] = []
    occupied: list[_Rect] = []

    for entry in entries:
        aspect = 1.5 if entry.target_area > 15 else 1.2
        w = math.sqrt(max(entry.target_area * aspect, 0.64))
        h = max(entry.target_area / w, 0.8)

        candidates = _edge_to_corners(entry.prefer_edge, constraints.entrance_side, entry.zone)
        if entry.corner_hint and entry.corner_hint not in candidates:
            candidates = [entry.corner_hint] + candidates

        best: _Rect | None = None
        for corner in candidates:
            rx0, ry0, rx1, ry1 = _snap_to_outline_corner(
                corner, w, h, min_x, min_y, max_x, max_y, poly,
            )
            rect = _Rect(rx0, ry0, rx1, ry1)
            if not _overlaps_any(rect, occupied, margin=0.08):
                best = rect
                entry.corner_hint = corner
                break
            adjusted = _nudge_rect_from_overlap(rect, occupied, corner, min_x, min_y, max_x, max_y)
            if adjusted and not _overlaps_any(adjusted, occupied, margin=0.05):
                best = adjusted
                entry.corner_hint = corner
                break

        if best is None:
            seed = hash(entry.name) % 100
            ax, ay = _find_interior_point(poly, seed=seed)
            best = _Rect(ax - w / 2, ay - h / 2, ax + w / 2, ay + h / 2)

        placed.append((entry.name, best))
        occupied.append(best)

    return placed


def _snap_to_outline_corner(
    corner: str,
    w: float,
    h: float,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    poly: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    if corner == "BL":
        rx0, ry0 = min_x + _EPS, min_y + _EPS
        rx1, ry1 = rx0 + w, ry0 + h
    elif corner == "BR":
        rx1, ry0 = max_x - _EPS, min_y + _EPS
        rx0, ry1 = rx1 - w, ry0 + h
    elif corner == "TL":
        rx0, ry1 = min_x + _EPS, max_y - _EPS
        rx1, ry0 = rx0 + w, ry1 - h
    else:
        rx1, ry1 = max_x - _EPS, max_y - _EPS
        rx0, ry0 = rx1 - w, ry1 - h

    rx0 = max(min_x + _EPS, min(rx0, max_x - _EPS))
    ry0 = max(min_y + _EPS, min(ry0, max_y - _EPS))
    rx1 = max(min_x + _EPS, min(rx1, max_x - _EPS))
    ry1 = max(min_y + _EPS, min(ry1, max_y - _EPS))

    cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
    if not point_in_polygon(cx, cy, poly):
        for scale in (0.9, 0.8, 0.7, 0.6, 0.5):
            sw, sh = w * scale, h * scale
            mx, my = (rx0 + rx1) / 2, (ry0 + ry1) / 2
            rx0, ry0 = mx - sw / 2, my - sh / 2
            rx1, ry1 = mx + sw / 2, my + sh / 2
            if point_in_polygon((rx0 + rx1) / 2, (ry0 + ry1) / 2, poly):
                break

    return rx0, ry0, rx1, ry1


def _overlaps_any(rect: _Rect, occupied: list[_Rect], margin: float = 0.05) -> bool:
    for o in occupied:
        if not (
            rect.x1 + margin <= o.x0
            or o.x1 + margin <= rect.x0
            or rect.y1 + margin <= o.y0
            or o.y1 + margin <= rect.y0
        ):
            return True
    return False


def _nudge_rect_from_overlap(
    rect: _Rect,
    occupied: list[_Rect],
    corner: str,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> _Rect | None:
    w, h = rect.w, rect.h
    shifts = [(0.5, 0), (-0.5, 0), (0, 0.5), (0, -0.5), (0.5, 0.5)]
    base_x0, base_y0 = rect.x0, rect.y0
    for dx, dy in shifts:
        nx0 = max(min_x, min(base_x0 + dx, max_x - w))
        ny0 = max(min_y, min(base_y0 + dy, max_y - h))
        candidate = _Rect(nx0, ny0, nx0 + w, ny0 + h)
        if not _overlaps_any(candidate, occupied, margin=0.05):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Remaining area → flexible rooms
# ---------------------------------------------------------------------------
def _compute_remaining_polygon(
    poly: list[tuple[float, float]],
    placed: list[tuple[str, _Rect]],
) -> list[list[tuple[float, float]]]:
    min_x, min_y, max_x, max_y = bbox_of_polygon(poly)
    step = 0.25
    rects = [r for _, r in placed]

    y_free: list[tuple[float, list[tuple[float, float]]]] = []
    y = min_y + step / 2
    while y < max_y:
        intervals = _x_intervals_inside(y, poly, min_x, max_x, step / 2)
        for r in rects:
            if r.y0 <= y <= r.y1:
                intervals = _subtract_interval(intervals, (r.x0 - 0.02, r.x1 + 0.02))
        if intervals:
            y_free.append((y, intervals))
        y += step

    if not y_free:
        return [poly]

    bands: list[list[tuple[float, list[tuple[float, float]]]]] = []
    current = [y_free[0]]
    for i in range(1, len(y_free)):
        prev_y = current[-1][0]
        cur_y, cur_iv = y_free[i]
        prev_iv = current[-1][1]
        same = (
            len(prev_iv) == len(cur_iv)
            and all(
                abs(a[0] - b[0]) < step * 3 and abs(a[1] - b[1]) < step * 3
                for a, b in zip(prev_iv, cur_iv)
            )
        )
        if same and abs(cur_y - prev_y) <= step * 1.5:
            current.append(y_free[i])
        else:
            bands.append(current)
            current = [y_free[i]]
    bands.append(current)

    result: list[list[tuple[float, float]]] = []
    for band in bands:
        if len(band) < 2:
            continue
        n_iv = len(band[0][1])
        y_top = max(band[0][0] - step / 2, min_y)
        y_bot = min(band[-1][0] + step / 2, max_y)

        wide_ivs: list[tuple[float, float]] = []
        for k in range(n_iv):
            lo = max(min(strip[1][k][0] for strip in band), min_x)
            hi = min(max(strip[1][k][1] for strip in band), max_x)
            if hi - lo > 0.3:
                wide_ivs.append((lo, hi))

        if not wide_ivs:
            continue

        pts: list[tuple[float, float]] = []
        for x0, x1 in wide_ivs:
            pts.append((x0, y_top))
            pts.append((x1, y_top))
        for x0, x1 in reversed(wide_ivs):
            pts.append((x1, y_bot))
            pts.append((x0, y_bot))

        pts = _simplify_polygon(pts)
        if len(pts) >= 3 and polygon_area(pts) > 0.5:
            result.append(pts)

    return result if result else [poly]


def _x_intervals_inside(
    y: float,
    poly: list[tuple[float, float]],
    min_x: float,
    max_x: float,
    step: float,
) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    x = min_x + step / 2
    in_interval = False
    start_x = 0.0
    while x < max_x:
        inside = point_in_polygon(x, y, poly)
        if inside and not in_interval:
            start_x = x - step / 2
            in_interval = True
        elif not inside and in_interval:
            intervals.append((start_x, x + step / 2))
            in_interval = False
        x += step
    if in_interval:
        intervals.append((start_x, max_x))
    return intervals


def _subtract_interval(
    intervals: list[tuple[float, float]],
    sub: tuple[float, float],
) -> list[tuple[float, float]]:
    sx0, sx1 = sub
    result: list[tuple[float, float]] = []
    for a, b in intervals:
        if sx1 <= a or sx0 >= b:
            result.append((a, b))
        else:
            if a < sx0:
                result.append((a, sx0))
            if sx1 < b:
                result.append((sx1, b))
    return result


def _simplify_polygon(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(pts) < 3:
        return pts
    result: list[tuple[float, float]] = [pts[0]]
    for i in range(1, len(pts)):
        if abs(pts[i][0] - result[-1][0]) > 0.01 or abs(pts[i][1] - result[-1][1]) > 0.01:
            result.append(pts[i])
    while (
        len(result) > 1
        and abs(result[-1][0] - result[0][0]) < 0.01
        and abs(result[-1][1] - result[0][1]) < 0.01
    ):
        result.pop()
    return result


def _poly_centroid(pts: list[tuple[float, float]]) -> tuple[float, float]:
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _dist_to_entrance(pts: list[tuple[float, float]], entrance_mid: tuple[float, float]) -> float:
    cx, cy = _poly_centroid(pts)
    return math.hypot(cx - entrance_mid[0], cy - entrance_mid[1])


def _assign_remaining_to_flex(
    remaining_polys: list[list[tuple[float, float]]],
    flex: list[_RoomEntry],
    outline_poly: list[tuple[float, float]],
    constraints: LLMConstraints,
) -> list[tuple[str, list[tuple[float, float]]]]:
    if not flex:
        return []
    if not remaining_polys:
        return _fallback_flex_rects(flex, outline_poly)

    polys_sorted = sorted(remaining_polys, key=lambda p: polygon_area(p), reverse=True)
    living_first = _living_must_near_entrance(constraints)

    if living_first and any(f.name == "客厅" for f in flex):
        polys_sorted = sorted(
            polys_sorted,
            key=lambda p: _dist_to_entrance(p, constraints.entrance_mid),
        )

    result: list[tuple[str, list[tuple[float, float]]]] = []
    flex_sorted = sorted(flex, key=lambda e: (0 if e.name == "客厅" else 1, -e.target_area))

    if len(flex_sorted) == 1:
        result.append((flex_sorted[0].name, polys_sorted[0]))
    elif len(polys_sorted) >= len(flex_sorted):
        for i, f in enumerate(flex_sorted):
            result.append((f.name, polys_sorted[i]))
    else:
        largest = polys_sorted[0]
        min_px, min_py, max_px, max_py = bbox_of_polygon(largest)
        mid = (min_px + max_px) / 2
        left_pts = [(x, y) for x, y in largest if x <= mid + 0.3]
        right_pts = [(x, y) for x, y in largest if x >= mid - 0.3]
        for i in range(len(largest)):
            ax, ay = largest[i]
            bx, by = largest[(i + 1) % len(largest)]
            if (ax - mid) * (bx - mid) < 0:
                t = (mid - ax) / (bx - ax + 1e-12)
                iy = ay + t * (by - ay)
                left_pts.append((mid, iy))
                right_pts.append((mid, iy))
        result.append((flex_sorted[0].name, _simplify_polygon(left_pts)))
        if len(flex_sorted) > 1:
            result.append((flex_sorted[1].name, _simplify_polygon(right_pts)))
        for f in flex_sorted[2:]:
            seed = hash(f.name) % 100
            ax, ay = _find_interior_point(outline_poly, seed=seed)
            result.append(
                (
                    f.name,
                    [
                        (ax - 1, ay - 1),
                        (ax + 1, ay - 1),
                        (ax + 1, ay + 1),
                        (ax - 1, ay + 1),
                    ],
                )
            )

    return result


def _fallback_flex_rects(
    flex: list[_RoomEntry],
    outline_poly: list[tuple[float, float]],
) -> list[tuple[str, list[tuple[float, float]]]]:
    min_x, min_y, max_x, max_y = bbox_of_polygon(outline_poly)
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    w = max(max_x - min_x - 1.0, 2.0)
    h = max(max_y - min_y - 1.0, 2.0)
    result: list[tuple[str, list[tuple[float, float]]]] = []
    for i, f in enumerate(flex):
        ox = (i % 2) * (w / 2 + 0.2)
        pts = [
            (cx - w / 2 + ox, cy - h / 2),
            (cx - w / 4 + ox, cy - h / 2),
            (cx - w / 4 + ox, cy + h / 2),
            (cx - w / 2 + ox, cy + h / 2),
        ]
        result.append((f.name, pts))
    return result


# ---------------------------------------------------------------------------
# Build LayoutRoom list
# ---------------------------------------------------------------------------
def _is_axis_aligned_rect_polygon(pts: list[tuple[float, float]], tol: float = 0.08) -> bool:
    if len(pts) != 4:
        return False
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return len(set(round(x, 2) for x in xs)) <= 2 and len(set(round(y, 2) for y in ys)) <= 2


def _make_rooms(
    placed_rects: list[tuple[str, _Rect]],
    flex_polys: list[tuple[str, list[tuple[float, float]]]],
    poly: list[tuple[float, float]],
    outline: SiteOutline,
) -> list[LayoutRoom]:
    del outline
    rooms: list[LayoutRoom] = []
    idx = 0

    for name, r in placed_rects:
        idx += 1
        rx0, ry0, rx1, ry1 = shrink_rect_into_polygon(
            r.x0, r.y0, r.x1, r.y1, poly, seed=idx,
        )
        rooms.append(
            LayoutRoom(
                id=f"r{idx}",
                name=name,
                type=name,
                polygon=rect_to_polygon(rx0, ry0, rx1, ry1),
                area_sqm=round(rect_area(rx0, ry0, rx1, ry1), 1),
                adjacent_to=[],
            )
        )

    for name, pts in flex_polys:
        idx += 1
        pts = _simplify_polygon(pts)
        if len(pts) < 3:
            continue
        area = round(polygon_area(pts), 1)
        if _is_axis_aligned_rect_polygon(pts):
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            rooms.append(
                LayoutRoom(
                    id=f"r{idx}",
                    name=name,
                    type=name,
                    polygon=rect_to_polygon(min(xs), min(ys), max(xs), max(ys)),
                    area_sqm=area,
                    adjacent_to=[],
                )
            )
        else:
            rooms.append(
                LayoutRoom(
                    id=f"r{idx}",
                    name=name,
                    type=name,
                    polygon=[Point2D(x=x, y=y) for x, y in pts],
                    area_sqm=area,
                    adjacent_to=[],
                )
            )

    _compute_adjacency(rooms)
    return rooms


def _compute_adjacency(rooms: list[LayoutRoom]) -> None:
    threshold = 0.35
    for i, r1 in enumerate(rooms):
        x0a, y0a, x1a, y1a = _room_bbox(r1)
        for j, r2 in enumerate(rooms):
            if i == j:
                continue
            x0b, y0b, x1b, y1b = _room_bbox(r2)
            if _edges_close(x0a, y0a, x1a, y1a, x0b, y0b, x1b, y1b, threshold):
                if r2.id not in r1.adjacent_to:
                    r1.adjacent_to.append(r2.id)


def _room_bbox(room: LayoutRoom) -> tuple[float, float, float, float]:
    xs = [p.x for p in room.polygon]
    ys = [p.y for p in room.polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _edges_close(
    x0a: float, y0a: float, x1a: float, y1a: float,
    x0b: float, y0b: float, x1b: float, y1b: float,
    thr: float,
) -> bool:
    h_overlap = min(x1a, x1b) - max(x0a, x0b) > thr
    v_overlap = min(y1a, y1b) - max(y0a, y0b) > thr
    if h_overlap and (abs(y1a - y0b) < thr or abs(y1b - y0a) < thr):
        return True
    if v_overlap and (abs(x1a - x0b) < thr or abs(x1b - x0a) < thr):
        return True
    return False


# ---------------------------------------------------------------------------
# Entrance side
# ---------------------------------------------------------------------------
def _get_entrance_side(
    outline: SiteOutline,
    min_x: float, min_y: float,
    max_x: float, max_y: float,
) -> str:
    if len(outline.entrance_edge) < 2:
        return "bottom"
    ei, ej = outline.entrance_edge[0], outline.entrance_edge[1]
    if ei >= len(outline.vertices) or ej >= len(outline.vertices):
        return "bottom"
    v1, v2 = outline.vertices[ei], outline.vertices[ej]
    mx, my = (v1.x + v2.x) / 2, (v1.y + v2.y) / 2
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    bw = max(max_x - min_x, 0.1)
    bh = max(max_y - min_y, 0.1)
    dx = (mx - cx) / bw
    dy = (my - cy) / bh
    if abs(dx) > abs(dy):
        return "right" if dx > 0 else "left"
    return "top" if dy > 0 else "bottom"
