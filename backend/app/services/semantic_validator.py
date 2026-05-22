"""Validate semantic layout covers planner room program (no geometry)."""

from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import LayoutBand, RoomPlacement, SemanticLayoutPlan


def validate_semantic_plan(plan: PlannerFinalPlan, semantic: SemanticLayoutPlan) -> list[str]:
    errors: list[str] = []
    required: dict[str, int] = {}
    for item in plan.space_program:
        required[item.room_type] = required.get(item.room_type, 0) + max(1, item.count)

    in_bands: dict[str, int] = {}
    for band in semantic.bands:
        for name in band.order:
            in_bands[name] = in_bands.get(name, 0) + 1

    in_placements = {p.room_type for p in semantic.placements}

    for room_type, need in required.items():
        got = in_bands.get(room_type, 0)
        if got < need and room_type not in in_placements:
            errors.append(f"语义布局缺少房间「{room_type}」（需要 {need}，bands 中出现 {got} 次）。")
        elif got < need and room_type in in_placements and not semantic.bands:
            errors.append(f"请把「{room_type}」加入 bands.order。")

    if not semantic.bands or not any(b.order for b in semantic.bands):
        if not semantic.placements:
            errors.append("bands 与 placements 均为空，无法编译布局。")
        else:
            errors.append("缺少 bands 条带顺序，将使用 cluster 自动分区。")

    return errors


def _unique_room_label(room_type: str, index: int, total: int) -> str:
    if total <= 1:
        return room_type
    return f"{room_type}{index}"


def reconcile_semantic_with_program(
    plan: PlannerFinalPlan,
    semantic: SemanticLayoutPlan,
) -> SemanticLayoutPlan:
    """Expand bands/placements so instance count matches space_program."""
    counts: dict[str, int] = {}
    for item in plan.space_program:
        counts[item.room_type] = counts.get(item.room_type, 0) + max(1, item.count)

    new_bands: list[LayoutBand] = []
    if semantic.bands:
        for band in semantic.bands:
            order: list[str] = []
            for name in band.order:
                total = counts.get(name, 1)
                for idx in range(1, total + 1):
                    order.append(_unique_room_label(name, idx, total))
            if order:
                new_bands.append(LayoutBand(order=order))

    placement_by_type: dict[str, list] = {}
    for p in semantic.placements:
        placement_by_type.setdefault(p.room_type, []).append(p)

    new_placements: list[RoomPlacement] = []
    for item in plan.space_program:
        total = max(1, item.count)
        templates = placement_by_type.get(item.room_type, [])
        for idx in range(1, total + 1):
            tpl = templates[idx - 1] if idx <= len(templates) else (templates[0] if templates else None)
            if tpl:
                new_placements.append(tpl.model_copy(update={"index": idx}))
            else:
                new_placements.append(RoomPlacement(room_type=item.room_type, index=idx))

    def _base_type(label: str) -> str:
        if label and label[-1].isdigit():
            i = len(label) - 1
            while i > 0 and label[i - 1].isdigit():
                i -= 1
            if i < len(label) and label[i:].isdigit():
                return label[:i]
        return label

    represented: set[str] = set()
    for band in new_bands:
        for label in band.order:
            represented.add(_base_type(label))

    missing: list[str] = []
    for room_type, total in counts.items():
        if room_type in represented:
            continue
        for idx in range(1, total + 1):
            missing.append(_unique_room_label(room_type, idx, total))

    if missing:
        if new_bands:
            last = list(new_bands[-1].order) + missing
            new_bands[-1] = LayoutBand(order=last)
        else:
            new_bands = [LayoutBand(order=missing)]

    updates: dict = {}
    if new_bands:
        updates["bands"] = new_bands
    if new_placements:
        updates["placements"] = new_placements
    if not updates:
        return semantic
    return semantic.model_copy(update=updates)
