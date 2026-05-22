"""Rule-based SemanticLayoutPlan when LLM is unavailable."""

from __future__ import annotations

from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import AdjacencyIntent, LayoutBand, RoomPlacement, SemanticLayoutPlan
from app.services.room_layout_conventions import (
    build_default_bands,
    merge_avoid_lists,
    merge_near_lists,
    prefer_edge_for,
    zone_for,
)

_PUBLIC = frozenset({"客厅", "餐厅", "厨房", "阳台", "玄关", "起居", "客餐厅"})
_PRIVATE = frozenset({"主卧", "次卧", "书房", "卧室", "儿童房"})
_SERVICE = frozenset({"卫生间", "主卫", "客卫", "洗手间"})


def _cluster_for(room_type: str) -> str:
    if room_type in _PUBLIC:
        return "public"
    if room_type in _PRIVATE or room_type == "卧室":
        return "private"
    if room_type in _SERVICE:
        return "service"
    return "other"


def _apply_default_position_hints(
    placements: list[RoomPlacement],
    bands: list[LayoutBand],
) -> None:
    """Assign normalized center/size so rule fallback matches strip layout."""
    n_bands = max(1, len(bands))
    slot_map: dict[tuple[str, int], tuple[float, float, float, float]] = {}
    type_seen: dict[str, int] = {}

    for bi, band in enumerate(bands):
        order = band.order or []
        n_rooms = max(1, len(order))
        band_h = 0.88 / n_bands
        cy = band_h * (bi + 0.5)
        for ri, room_type in enumerate(order):
            type_seen[room_type] = type_seen.get(room_type, 0) + 1
            idx = type_seen[room_type]
            wr = min(0.45, 0.82 / n_rooms)
            hr = min(0.42, band_h * 0.95)
            cx = (ri + 0.5) / n_rooms
            slot_map[(room_type, idx)] = (cx, cy, wr, hr)

    per_type_idx: dict[str, int] = {}
    for p in placements:
        per_type_idx[p.room_type] = per_type_idx.get(p.room_type, 0) + 1
        idx = p.index if p.index > 0 else per_type_idx[p.room_type]
        key = (p.room_type, idx)
        if key not in slot_map:
            key = (p.room_type, per_type_idx[p.room_type])
        if key in slot_map:
            cx, cy, wr, hr = slot_map[key]
            p.center_x = cx
            p.center_y = cy
            p.width_ratio = wr
            p.height_ratio = hr


def _zone_for(room_type: str, cluster: str) -> str:
    if room_type == "玄关" or room_type.endswith("玄关"):
        return "near_entrance"
    if cluster == "public":
        return "south"
    if cluster == "private":
        return "north"
    if cluster == "service":
        return "center"
    return "center"


def _extract_prefer_edge(notes: str, room_type: str) -> str:
    """Extract position preference from room notes.

    Converts Chinese position hints to edge labels used by grid compiler.
    """
    # Default edge preferences by room type
    defaults = prefer_edge_for(room_type) or ""
    if not notes:
        return defaults

    pos_map = {
        "右下": "south", "左下": "south", "下": "south", "南侧": "south", "南": "south",
        "右上": "north", "左上": "north", "上": "north", "北侧": "north", "北": "north",
        "右侧": "east", "右": "east", "东侧": "east", "东": "east",
        "左侧": "west", "左": "west", "西侧": "west", "西": "west",
        "中间": "", "中心": "",
    }
    for kw, edge in pos_map.items():
        if kw in notes:
            return edge
    return defaults or prefer_edge_for(room_type, "")


def build_default_semantic_plan(plan: PlannerFinalPlan) -> SemanticLayoutPlan:
    placements: list[RoomPlacement] = []
    public_order: list[str] = []
    private_order: list[str] = []
    service_order: list[str] = []

    for item in plan.space_program:
        cluster = _cluster_for(item.room_type)
        zone = zone_for(item.room_type, _zone_for(item.room_type, cluster))
        size = "large" if (item.target_area_sqm or 0) >= 14 else "medium" if (item.target_area_sqm or 0) >= 8 else "small"
        prefer_edge = _extract_prefer_edge(item.notes or "", item.room_type)
        prefer_edge = prefer_edge_for(item.room_type, prefer_edge)
        near = merge_near_lists([], item.room_type)
        avoid = merge_avoid_lists([], item.room_type)
        for idx in range(max(1, item.count)):
            name = item.room_type if item.count == 1 else f"{item.room_type}{idx + 1}"
            placements.append(
                RoomPlacement(
                    room_type=item.room_type,
                    zone=zone,  # type: ignore[arg-type]
                    size=size,  # type: ignore[arg-type]
                    cluster=cluster,  # type: ignore[arg-type]
                    prefer_edge=prefer_edge,
                    near=near,
                    avoid=avoid,
                    index=idx + 1,
                )
            )
            if cluster == "public" and name not in public_order:
                public_order.append(item.room_type)
            elif cluster == "private" and item.room_type not in private_order:
                private_order.append(item.room_type)
            elif cluster == "service" and item.room_type not in service_order:
                service_order.append(item.room_type)

    # Strip bands: 北卧区 → 厨卫服务带 → 南阳台；客厅/餐厅由 flexible 填充在南侧
    band_rows = build_default_bands(public_order, private_order, service_order)
    bands = [LayoutBand(order=row) for row in band_rows if row]

    if not bands and placements:
        bands = [LayoutBand(order=[p.room_type for p in placements])]

    adjacency_intent: list[AdjacencyIntent] = []
    for a, b, strength in (
        ("厨房", "餐厅", "must"),
        ("餐厅", "客厅", "prefer"),
        ("客厅", "阳台", "prefer"),
        ("主卧", "卫生间", "prefer"),
    ):
        if any(p.room_type == a for p in placements) and any(p.room_type == b for p in placements):
            adjacency_intent.append(AdjacencyIntent(a=a, b=b, strength=strength))

    _apply_default_position_hints(placements, bands)

    entrance = "玄关" if any(p.room_type == "玄关" for p in placements) else ""
    if not entrance:
        for p in placements:
            if p.zone == "near_entrance":
                entrance = p.room_type
                break

    return SemanticLayoutPlan(
        layout_style="strip",
        strip_direction="horizontal",
        public_side="south",
        entrance_room=entrance,
        placements=placements,
        bands=bands,
        adjacency_intent=adjacency_intent,
    )
