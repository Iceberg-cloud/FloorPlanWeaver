"""Post-process layout drafts: clip, de-overlap, snap neighbors (no doors/windows)."""

from __future__ import annotations

from app.schemas.layout import LayoutDraft, LayoutRoom, SiteOutline
from app.schemas.planner import PlannerFinalPlan
from app.services.layout_adhesion import fill_outline_coverage
from app.services.layout_geometry import (
    bbox_of_polygon,
    rect_area,
    rect_from_points,
    rects_overlap,
    shrink_rect_into_polygon,
    update_room_rect,
)

# Maximum distance (meters) to consider two rooms "almost touching" for snap
_SNAP_THRESHOLD = 0.35
_ADHESION_GAP = 0.55
_EXPAND_STEP = 0.12


def postprocess_layout(
    layout: LayoutDraft,
    outline: SiteOutline | None,
    plan: PlannerFinalPlan | None,
) -> tuple[LayoutDraft, list[str]]:
    """Light post-processing: clip + fix overlaps + snap neighbors."""
    notes: list[str] = []
    if not layout.rooms:
        return layout, notes

    poly: list[tuple[float, float]] = []
    if outline and outline.vertices:
        poly = [(v.x, v.y) for v in outline.vertices]
        layout.outline_vertices = outline.vertices
        layout.entrance_edge = outline.entrance_edge

    rooms: list[tuple[LayoutRoom, tuple[float, float, float, float]]] = []
    for room in layout.rooms:
        if not room.polygon:
            continue
        x0, y0, x1, y1 = rect_from_points(room.polygon)
        rooms.append((room, (x0, y0, x1, y1)))

    # Step 1: Clip all rooms into outline
    if poly:
        clipped = 0
        for i, (room, rect) in enumerate(rooms):
            x0, y0, x1, y1 = rect
            nx0, ny0, nx1, ny1 = shrink_rect_into_polygon(x0, y0, x1, y1, poly, seed=i)
            if (nx0, ny0, nx1, ny1) != (x0, y0, x1, y1):
                clipped += 1
            rooms[i] = (_update_room_rect(room, nx0, ny0, nx1, ny1), (nx0, ny0, nx1, ny1))
        if clipped:
            notes.append(f"已将 {clipped} 个房间裁剪至外轮廓内。")

    # Step 2: Resolve overlaps (push apart + shrink)
    separated = _resolve_overlaps(rooms)
    if separated:
        notes.append(f"已分离 {separated} 处房间重叠。")

    # Step 3: Re-clip after overlap resolution
    if poly:
        for i, (room, rect) in enumerate(rooms):
            x0, y0, x1, y1 = rect
            nx0, ny0, nx1, ny1 = shrink_rect_into_polygon(x0, y0, x1, y1, poly, seed=i)
            rooms[i] = (_update_room_rect(room, nx0, ny0, nx1, ny1), (nx0, ny0, nx1, ny1))

    # Step 4: Snap room edges to neighbors (eliminate gaps)
    if poly and len(rooms) > 1:
        snapped = _snap_rooms_to_neighbors(rooms, poly)
        if snapped:
            notes.append(f"已对齐 {snapped} 处房间邻接边。")

    # Step 5: Adhesion — close gaps and expand rooms to fill outline
    if poly and len(rooms) > 1:
        closed = _close_neighbor_gaps(rooms, poly)
        expanded = _expand_rooms_to_fill(rooms, poly)
        rooms, boosted = fill_outline_coverage(rooms, poly)
        if closed or expanded or boosted:
            notes.append(
                f"吸附填满：闭合 {closed} 处邻接缝，扩展 {expanded} 条边，"
                f"强化填充 {boosted} 次以布满外轮廓。"
            )
        _snap_rooms_to_neighbors(rooms, poly)
        _close_neighbor_gaps(rooms, poly)

    # Step 6: Final overlap check after adhesion
    _resolve_overlaps(rooms)

    layout.rooms = [r for r, _ in rooms]
    return layout, notes


def normalize_rooms_to_rects(layout: LayoutDraft) -> LayoutDraft:
    """LLM may return irregular polygons; use AABB for post-processing."""
    rooms: list[LayoutRoom] = []
    for room in layout.rooms:
        if not room.polygon:
            continue
        x0, y0, x1, y1 = rect_from_points(room.polygon)
        rooms.append(_update_room_rect(room, x0, y0, x1, y1))
    return layout.model_copy(update={"rooms": rooms})


def _update_room_rect(room: LayoutRoom, x0: float, y0: float, x1: float, y1: float) -> LayoutRoom:
    return update_room_rect(room, x0, y0, x1, y1)


def _resolve_overlaps(rooms: list[tuple[LayoutRoom, tuple[float, float, float, float]]]) -> int:
    fixes = 0
    for _ in range(48):
        moved = False
        for i in range(len(rooms)):
            for j in range(i + 1, len(rooms)):
                ri, rect_i = rooms[i]
                rj, rect_j = rooms[j]
                if not rects_overlap(rect_i, rect_j, gap=0.02):
                    continue
                ax0, ay0, ax1, ay1 = rect_i
                bx0, by0, bx1, by1 = rect_j

                overlap_x = min(ax1, bx1) - max(ax0, bx0)
                overlap_y = min(ay1, by1) - max(ay0, by0)
                if overlap_x > 0 and overlap_y > 0:
                    if overlap_x < overlap_y:
                        shift = (overlap_x / 2) + 0.08
                        if ax0 < bx0:
                            ax0 -= shift; ax1 -= shift
                            bx0 += shift; bx1 += shift
                        else:
                            ax0 += shift; ax1 += shift
                            bx0 -= shift; bx1 -= shift
                    else:
                        shift = (overlap_y / 2) + 0.08
                        if ay0 < by0:
                            ay0 -= shift; ay1 -= shift
                            by0 += shift; by1 += shift
                        else:
                            ay0 += shift; ay1 += shift
                            by0 -= shift; by1 -= shift
                    rooms[i] = (_update_room_rect(ri, ax0, ay0, ax1, ay1), (ax0, ay0, ax1, ay1))
                    rooms[j] = (_update_room_rect(rj, bx0, by0, bx1, by1), (bx0, by0, bx1, by1))
                    moved = True
                    fixes += 1
                    continue

                area_i = rect_area(*rect_i)
                area_j = rect_area(*rect_j)
                if area_i <= area_j:
                    cx, cy = (ax0 + ax1) / 2, (ay0 + ay1) / 2
                    hw, hh = (ax1 - ax0) / 2 * 0.85, (ay1 - ay0) / 2 * 0.85
                    ax0, ay0, ax1, ay1 = cx - hw, cy - hh, cx + hw, cy + hh
                    rooms[i] = (_update_room_rect(ri, ax0, ay0, ax1, ay1), (ax0, ay0, ax1, ay1))
                else:
                    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
                    hw, hh = (bx1 - bx0) / 2 * 0.85, (by1 - by0) / 2 * 0.85
                    bx0, by0, bx1, by1 = cx - hw, cy - hh, cx + hw, cy + hh
                    rooms[j] = (_update_room_rect(rj, bx0, by0, bx1, by1), (bx0, by0, bx1, by1))
                moved = True
                fixes += 1
        if not moved:
            break
    return fixes


# ---------------------------------------------------------------------------
# Snap-to-neighbor: align room edges to eliminate gaps
# ---------------------------------------------------------------------------
def _snap_rooms_to_neighbors(
    rooms: list[tuple[LayoutRoom, tuple[float, float, float, float]]],
    poly: list[tuple[float, float]],
) -> int:
    """Snap each room's edges to adjacent rooms or outline boundary.

    Returns the number of edges snapped.
    """
    if not poly:
        return 0
    ol_min_x, ol_min_y, ol_max_x, ol_max_y = bbox_of_polygon(poly)
    total_snapped = 0

    # Multiple passes to allow snap chains to propagate
    for _ in range(3):
        snap_count = 0
        for idx, (room, rect) in enumerate(rooms):
            rx0, ry0, rx1, ry1 = rect

            # Find left neighbors (their right edge is close to my left edge)
            left_vals: list[float] = []
            for j, (_, other_rect) in enumerate(rooms):
                if j == idx:
                    continue
                ox0, oy0, ox1, oy1 = other_rect
                # Other's right edge near my left edge
                if abs(ox1 - rx0) < _SNAP_THRESHOLD and _v_overlap(ry0, ry1, oy0, oy1) > 0.3:
                    left_vals.append(ox1)

            # Find right neighbors
            right_vals: list[float] = []
            for j, (_, other_rect) in enumerate(rooms):
                if j == idx:
                    continue
                ox0, oy0, ox1, oy1 = other_rect
                if abs(ox0 - rx1) < _SNAP_THRESHOLD and _v_overlap(ry0, ry1, oy0, oy1) > 0.3:
                    right_vals.append(ox0)

            # Find bottom neighbors
            bottom_vals: list[float] = []
            for j, (_, other_rect) in enumerate(rooms):
                if j == idx:
                    continue
                ox0, oy0, ox1, oy1 = other_rect
                if abs(oy1 - ry0) < _SNAP_THRESHOLD and _h_overlap(rx0, rx1, ox0, ox1) > 0.3:
                    bottom_vals.append(oy1)

            # Find top neighbors
            top_vals: list[float] = []
            for j, (_, other_rect) in enumerate(rooms):
                if j == idx:
                    continue
                ox0, oy0, ox1, oy1 = other_rect
                if abs(oy0 - ry1) < _SNAP_THRESHOLD and _h_overlap(rx0, rx1, ox0, ox1) > 0.3:
                    top_vals.append(oy0)

            # Snap left edge
            new_rx0 = rx0
            if left_vals:
                new_rx0 = max(left_vals)  # align to the nearest neighbor's right edge
            else:
                # Snap to outline left boundary if close
                if abs(rx0 - ol_min_x) < _SNAP_THRESHOLD:
                    new_rx0 = ol_min_x

            # Snap right edge
            new_rx1 = rx1
            if right_vals:
                new_rx1 = min(right_vals)
            else:
                if abs(rx1 - ol_max_x) < _SNAP_THRESHOLD:
                    new_rx1 = ol_max_x

            # Snap bottom edge
            new_ry0 = ry0
            if bottom_vals:
                new_ry0 = max(bottom_vals)
            else:
                if abs(ry0 - ol_min_y) < _SNAP_THRESHOLD:
                    new_ry0 = ol_min_y

            # Snap top edge
            new_ry1 = ry1
            if top_vals:
                new_ry1 = min(top_vals)
            else:
                if abs(ry1 - ol_max_y) < _SNAP_THRESHOLD:
                    new_ry1 = ol_max_y

            # Ensure minimum size
            if new_rx1 - new_rx0 < 0.4:
                continue
            if new_ry1 - new_ry0 < 0.4:
                continue

            # Clip to outline
            new_rx0, new_ry0, new_rx1, new_ry1 = shrink_rect_into_polygon(
                new_rx0, new_ry0, new_rx1, new_ry1, poly, seed=idx,
            )

            if (new_rx0, new_ry0, new_rx1, new_ry1) != (rx0, ry0, rx1, ry1):
                snap_count += 1
                rooms[idx] = (_update_room_rect(room, new_rx0, new_ry0, new_rx1, new_ry1),
                              (new_rx0, new_ry0, new_rx1, new_ry1))

        total_snapped += snap_count
        if snap_count == 0:
            break

    return total_snapped


def _v_overlap(y0a: float, y1a: float, y0b: float, y1b: float) -> float:
    """Vertical overlap length between two intervals."""
    return max(0.0, min(y1a, y1b) - max(y0a, y0b))


def _h_overlap(x0a: float, x1a: float, x0b: float, x1b: float) -> float:
    """Horizontal overlap length between two intervals."""
    return max(0.0, min(x1a, x1b) - max(x0a, x0b))


def _close_neighbor_gaps(
    rooms: list[tuple[LayoutRoom, tuple[float, float, float, float]]],
    poly: list[tuple[float, float]],
) -> int:
    """Pull facing edges together when a small gap remains between neighbors."""
    closed = 0
    ol_min_x, ol_min_y, ol_max_x, ol_max_y = bbox_of_polygon(poly)

    for _ in range(4):
        moved = False
        for i in range(len(rooms)):
            ri, (ax0, ay0, ax1, ay1) = rooms[i]
            for j in range(i + 1, len(rooms)):
                rj, (bx0, by0, bx1, by1) = rooms[j]

                # A left of B
                if ax1 < bx0 and _v_overlap(ay0, ay1, by0, by1) > 0.25:
                    gap = bx0 - ax1
                    if 0.02 < gap < _ADHESION_GAP:
                        mid = (ax1 + bx0) / 2
                        rooms[i] = (_update_room_rect(ri, ax0, ay0, mid, ay1), (ax0, ay0, mid, ay1))
                        rooms[j] = (_update_room_rect(rj, mid, by0, bx1, by1), (mid, by0, bx1, by1))
                        moved = True
                        closed += 1

                # B left of A
                if bx1 < ax0 and _v_overlap(by0, by1, ay0, ay1) > 0.25:
                    gap = ax0 - bx1
                    if 0.02 < gap < _ADHESION_GAP:
                        mid = (bx1 + ax0) / 2
                        rooms[j] = (_update_room_rect(rj, bx0, by0, mid, by1), (bx0, by0, mid, by1))
                        rooms[i] = (_update_room_rect(ri, mid, ay0, ax1, ay1), (mid, ay0, ax1, ay1))
                        moved = True
                        closed += 1

                # A below B
                if ay1 < by0 and _h_overlap(ax0, ax1, bx0, bx1) > 0.25:
                    gap = by0 - ay1
                    if 0.02 < gap < _ADHESION_GAP:
                        mid = (ay1 + by0) / 2
                        rooms[i] = (_update_room_rect(ri, ax0, ay0, ax1, mid), (ax0, ay0, ax1, mid))
                        rooms[j] = (_update_room_rect(rj, bx0, mid, bx1, by1), (bx0, mid, bx1, by1))
                        moved = True
                        closed += 1

                # B below A
                if by1 < ay0 and _h_overlap(bx0, bx1, ax0, ax1) > 0.25:
                    gap = ay0 - by1
                    if 0.02 < gap < _ADHESION_GAP:
                        mid = (by1 + ay0) / 2
                        rooms[j] = (_update_room_rect(rj, bx0, by0, bx1, mid), (bx0, by0, bx1, mid))
                        rooms[i] = (_update_room_rect(ri, ax0, mid, ax1, ay1), (ax0, mid, ax1, ay1))
                        moved = True
                        closed += 1

        if not moved:
            break

    # Snap outer edges to outline when close
    for idx, (room, rect) in enumerate(rooms):
        x0, y0, x1, y1 = rect
        nx0, ny0, nx1, ny1 = x0, y0, x1, y1
        if abs(x0 - ol_min_x) < _ADHESION_GAP:
            nx0 = ol_min_x
        if abs(x1 - ol_max_x) < _ADHESION_GAP:
            nx1 = ol_max_x
        if abs(y0 - ol_min_y) < _ADHESION_GAP:
            ny0 = ol_min_y
        if abs(y1 - ol_max_y) < _ADHESION_GAP:
            ny1 = ol_max_y
        if (nx0, ny0, nx1, ny1) != (x0, y0, x1, y1):
            nx0, ny0, nx1, ny1 = shrink_rect_into_polygon(nx0, ny0, nx1, ny1, poly, seed=idx)
            rooms[idx] = (_update_room_rect(room, nx0, ny0, nx1, ny1), (nx0, ny0, nx1, ny1))
            closed += 1

    return closed


def _expand_rooms_to_fill(
    rooms: list[tuple[LayoutRoom, tuple[float, float, float, float]]],
    poly: list[tuple[float, float]],
) -> int:
    """Grow room rectangles into free space until blocked by neighbors or outline."""
    expanded_edges = 0
    ol_min_x, ol_min_y, ol_max_x, ol_max_y = bbox_of_polygon(poly)

    for _ in range(24):
        any_growth = False
        rects = [r for _, r in rooms]

        for idx, (room, rect) in enumerate(rooms):
            x0, y0, x1, y1 = rect
            min_w, min_h = 0.45, 0.45

            left_vals = [
                ox1 for j, (ox0, oy0, ox1, oy1) in enumerate(rects)
                if j != idx and ox1 <= x0 + 0.02 and _v_overlap(y0, y1, oy0, oy1) > 0.2
            ]
            right_vals = [
                ox0 for j, (ox0, oy0, ox1, oy1) in enumerate(rects)
                if j != idx and ox0 >= x1 - 0.02 and _v_overlap(y0, y1, oy0, oy1) > 0.2
            ]
            bottom_vals = [
                oy1 for j, (ox0, oy0, ox1, oy1) in enumerate(rects)
                if j != idx and oy1 <= y0 + 0.02 and _h_overlap(x0, x1, ox0, ox1) > 0.2
            ]
            top_vals = [
                oy0 for j, (ox0, oy0, ox1, oy1) in enumerate(rects)
                if j != idx and oy0 >= y1 - 0.02 and _h_overlap(x0, x1, ox0, ox1) > 0.2
            ]
            left_room = max(left_vals) if left_vals else ol_min_x
            right_room = min(right_vals) if right_vals else ol_max_x
            bottom_room = max(bottom_vals) if bottom_vals else ol_min_y
            top_room = min(top_vals) if top_vals else ol_max_y

            nx0 = min(x0, left_room + _EXPAND_STEP) if x0 - left_room > 0.04 else x0
            nx1 = max(x1, right_room - _EXPAND_STEP) if right_room - x1 > 0.04 else x1
            ny0 = min(y0, bottom_room + _EXPAND_STEP) if y0 - bottom_room > 0.04 else y0
            ny1 = max(y1, top_room - _EXPAND_STEP) if top_room - y1 > 0.04 else y1

            if nx1 - nx0 < min_w or ny1 - ny0 < min_h:
                continue

            nx0, ny0, nx1, ny1 = shrink_rect_into_polygon(nx0, ny0, nx1, ny1, poly, seed=idx)
            if nx1 - nx0 < min_w or ny1 - ny0 < min_h:
                continue

            blocked = False
            for j, (_, other) in enumerate(rooms):
                if j == idx:
                    continue
                if rects_overlap((nx0, ny0, nx1, ny1), other, gap=0.01):
                    blocked = True
                    break
            if blocked:
                continue

            if (nx0, ny0, nx1, ny1) != (x0, y0, x1, y1):
                growth = (
                    int(nx0 < x0 - 1e-6) + int(nx1 > x1 + 1e-6)
                    + int(ny0 < y0 - 1e-6) + int(ny1 > y1 + 1e-6)
                )
                expanded_edges += growth
                rooms[idx] = (_update_room_rect(room, nx0, ny0, nx1, ny1), (nx0, ny0, nx1, ny1))
                any_growth = True

        if not any_growth:
            break

    return expanded_edges
