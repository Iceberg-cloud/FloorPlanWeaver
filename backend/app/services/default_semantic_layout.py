"""Rule-based SemanticLayoutPlan when LLM is unavailable."""

from __future__ import annotations

from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import LayoutBand, RoomPlacement, SemanticLayoutPlan

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


def build_default_semantic_plan(plan: PlannerFinalPlan) -> SemanticLayoutPlan:
    placements: list[RoomPlacement] = []
    public_order: list[str] = []
    private_order: list[str] = []
    service_order: list[str] = []

    for item in plan.space_program:
        cluster = _cluster_for(item.room_type)
        zone = _zone_for(item.room_type, cluster)
        size = "large" if (item.target_area_sqm or 0) >= 14 else "medium" if (item.target_area_sqm or 0) >= 8 else "small"
        for idx in range(max(1, item.count)):
            name = item.room_type if item.count == 1 else f"{item.room_type}{idx + 1}"
            placements.append(
                RoomPlacement(
                    room_type=item.room_type,
                    zone=zone,  # type: ignore[arg-type]
                    size=size,  # type: ignore[arg-type]
                    cluster=cluster,  # type: ignore[arg-type]
                    prefer_edge="south" if item.room_type in ("客厅", "阳台") else "",
                    index=idx + 1,
                )
            )
            if cluster == "public" and name not in public_order:
                public_order.append(item.room_type)
            elif cluster == "private" and item.room_type not in private_order:
                private_order.append(item.room_type)
            elif cluster == "service" and item.room_type not in service_order:
                service_order.append(item.room_type)

    # Strip bands: ① 卫/阳台/卧 ② 厨 ③ 客餐厅由 flexible 阶段填充
    bands: list[LayoutBand] = []
    row1: list[str] = []
    for key in ("阳台", "卫生间", "主卧", "次卧", "卧室", "儿童房"):
        for src in (service_order, private_order):
            if key in src and key not in row1:
                row1.append(key)
    for r in service_order + private_order:
        if r not in row1 and r not in ("厨房", "客厅", "餐厅", "起居室", "客餐厅"):
            row1.append(r)
    if row1:
        bands.append(LayoutBand(order=row1))

    row2: list[str] = []
    if "厨房" in public_order or "厨房" in private_order or "厨房" in service_order:
        row2.append("厨房")
    for r in public_order:
        if r == "厨房" and r not in row2:
            row2.append(r)
    if row2:
        bands.append(LayoutBand(order=row2))

    if not bands and placements:
        bands = [LayoutBand(order=[p.room_type for p in placements])]

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
    )
