"""Aggressive outline fill: expand rooms to tile the interior."""

from __future__ import annotations

from app.schemas.layout import LayoutRoom
from app.services.layout_geometry import (
    bbox_of_polygon,
    rects_overlap,
    shrink_rect_into_polygon,
    update_room_rect,
)

_EXPAND_STEP = 0.08
_MIN_ROOM = 0.4


def fill_outline_coverage(
    rooms: list[tuple[LayoutRoom, tuple[float, float, float, float]]],
    poly: list[tuple[float, float]],
    *,
    max_passes: int = 48,
) -> tuple[list[tuple[LayoutRoom, tuple[float, float, float, float]]], int]:
    """Expand rooms toward outline and neighbors until interior is mostly covered."""
    if not poly or not rooms:
        return rooms, 0

    ol_min_x, ol_min_y, ol_max_x, ol_max_y = bbox_of_polygon(poly)
    grown = 0

    for _ in range(max_passes):
        any_change = False
        rects = [r for _, r in rooms]

        for idx, (room, rect) in enumerate(rooms):
            x0, y0, x1, y1 = rect
            left_block = ol_min_x
            right_block = ol_max_x
            bottom_block = ol_min_y
            top_block = ol_max_y

            for j, other in enumerate(rects):
                if j == idx:
                    continue
                ox0, oy0, ox1, oy1 = other
                if ox1 <= x0 + 0.05 and _overlap_interval(y0, y1, oy0, oy1) > 0.15:
                    left_block = max(left_block, ox1)
                if ox0 >= x1 - 0.05 and _overlap_interval(y0, y1, oy0, oy1) > 0.15:
                    right_block = min(right_block, ox0)
                if oy1 <= y0 + 0.05 and _overlap_interval(x0, x1, ox0, ox1) > 0.15:
                    bottom_block = max(bottom_block, oy1)
                if oy0 >= y1 - 0.05 and _overlap_interval(x0, x1, ox0, ox1) > 0.15:
                    top_block = min(top_block, oy0)

            nx0 = max(ol_min_x, min(x0, left_block + _EXPAND_STEP))
            ny0 = max(ol_min_y, min(y0, bottom_block + _EXPAND_STEP))
            nx1 = min(ol_max_x, max(x1, right_block - _EXPAND_STEP))
            ny1 = min(ol_max_y, max(y1, top_block - _EXPAND_STEP))

            if nx1 - nx0 < _MIN_ROOM or ny1 - ny0 < _MIN_ROOM:
                continue

            nx0, ny0, nx1, ny1 = shrink_rect_into_polygon(nx0, ny0, nx1, ny1, poly, seed=idx)
            if nx1 - nx0 < _MIN_ROOM or ny1 - ny0 < _MIN_ROOM:
                continue

            blocked = False
            for j, other in enumerate(rects):
                if j == idx:
                    continue
                if rects_overlap((nx0, ny0, nx1, ny1), other, gap=0.01):
                    blocked = True
                    break
            if blocked:
                continue

            if (nx0, ny0, nx1, ny1) != (x0, y0, x1, y1):
                rooms[idx] = (
                    update_room_rect(room, nx0, ny0, nx1, ny1),
                    (nx0, ny0, nx1, ny1),
                )
                grown += 1
                any_change = True

        if not any_change:
            break

    # Prefer growing 客厅/餐厅 into any large leftover band
    grown += _boost_living_dining(rooms, poly)
    return rooms, grown


def _boost_living_dining(
    rooms: list[tuple[LayoutRoom, tuple[float, float, float, float]]],
    poly: list[tuple[float, float]],
) -> int:
    public_idx = [
        i for i, (r, _) in enumerate(rooms)
        if r.name in ("客厅", "餐厅", "起居室", "客餐厅") or r.type in ("客厅", "餐厅", "起居室", "客餐厅")
    ]
    if not public_idx:
        return 0

    ol_min_x, ol_min_y, ol_max_x, ol_max_y = bbox_of_polygon(poly)
    step = 0.15
    n = 0
    for _ in range(16):
        moved = False
        rects = [r for _, r in rooms]
        for idx in public_idx:
            room, (x0, y0, x1, y1) = rooms[idx]
            for nx0, ny0, nx1, ny1 in [
                (x0 - step, y0, x1, y1),
                (x0, y0, x1 + step, y1),
                (x0, y0 - step, x1, y1),
                (x0, y0, x1, y1 + step),
            ]:
                if nx1 - nx0 < _MIN_ROOM or ny1 - ny0 < _MIN_ROOM:
                    continue
                nx0, ny0, nx1, ny1 = shrink_rect_into_polygon(
                    max(ol_min_x, nx0), max(ol_min_y, ny0),
                    min(ol_max_x, nx1), min(ol_max_y, ny1),
                    poly, seed=idx,
                )
                if nx1 - nx0 < _MIN_ROOM or ny1 - ny0 < _MIN_ROOM:
                    continue
                if any(rects_overlap((nx0, ny0, nx1, ny1), o, 0.01) for j, o in enumerate(rects) if j != idx):
                    continue
                if (nx0, ny0, nx1, ny1) != (x0, y0, x1, y1):
                    rooms[idx] = (update_room_rect(room, nx0, ny0, nx1, ny1), (nx0, ny0, nx1, ny1))
                    moved = True
                    n += 1
        if not moved:
            break
    return n


def _overlap_interval(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))
