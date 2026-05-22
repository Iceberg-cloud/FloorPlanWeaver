"""Render LayoutDraft to SVG with Chinese labels, adaptive fonts, and precise centers."""
import math
from app.schemas.layout import LayoutDraft, Point2D


def render_layout_svg(layout: LayoutDraft) -> str:
    room_fill = {
        "客厅": "#dbeafe", "餐厅": "#fef3c7", "厨房": "#fce7f3",
        "主卧": "#dcfce7", "次卧": "#ede9fe", "卫生间": "#cffafe",
        "阳台": "#f9f9f9", "书房": "#e0e7ff", "玄关": "#ffedd5",
        "儿童房": "#fef9c3", "主卫": "#cffafe", "客卫": "#cffafe",
    }
    room_stroke = {
        "客厅": "#3b82f6", "餐厅": "#f59e0b", "厨房": "#ec4899",
        "主卧": "#22c55e", "次卧": "#8b5cf6", "卫生间": "#06b6d4",
        "阳台": "#94a3b8", "书房": "#6366f1", "玄关": "#f97316",
        "儿童房": "#eab308", "主卫": "#06b6d4", "客卫": "#06b6d4",
    }

    parts: list[str] = []

    # Background grid
    w = layout.canvas.get("width", 10)
    h = layout.canvas.get("height", 8)
    grid_step = 1
    for gx in range(int(w) + 2):
        parts.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{h}" stroke="#f1f5f9" stroke-width="0.03"/>')
    for gy in range(int(h) + 2):
        parts.append(f'<line x1="0" y1="{gy}" x2="{w}" y2="{gy}" stroke="#f1f5f9" stroke-width="0.03"/>')

    # Outline
    if layout.outline_vertices:
        pts = " ".join(f"{v.x:.2f},{v.y:.2f}" for v in layout.outline_vertices)
        parts.append(f'<polygon points="{pts}" fill="rgba(148,163,184,0.05)" '
                     f'stroke="#475569" stroke-width="0.1" stroke-linejoin="round"/>')

    # Rooms
    for room in layout.rooms:
        polygon = room.polygon
        if len(polygon) < 3:
            continue

        pts = " ".join(f"{p.x:.2f},{p.y:.2f}" for p in polygon)
        fill = room_fill.get(room.type, "#f5f5f5")
        stroke = room_stroke.get(room.type, "#94a3b8")
        parts.append(f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" '
                     f'stroke-width="0.06" stroke-linejoin="miter"/>')

        # Compute label center using bbox + point-in-polygon check
        cx, cy = _label_center(polygon, room.area_sqm)
        area = room.area_sqm

        # Adaptive font size based on room area
        if area >= 14:
            name_fs, area_fs = 0.38, 0.26
        elif area >= 8:
            name_fs, area_fs = 0.32, 0.22
        elif area >= 4:
            name_fs, area_fs = 0.26, 0.18
        else:
            name_fs, area_fs = 0.20, 0.14

        # For very small rooms, show only name on one line
        if area < 3:
            parts.append(f'<text x="{cx:.2f}" y="{cy + name_fs * 0.35:.2f}" '
                         f'text-anchor="middle" font-size="{name_fs}" '
                         f'fill="#1e293b" font-weight="600" font-family="sans-serif">{room.name}</text>')
        else:
            parts.append(f'<text x="{cx:.2f}" y="{cy - name_fs * 0.3:.2f}" '
                         f'text-anchor="middle" font-size="{name_fs}" '
                         f'fill="#1e293b" font-weight="600" font-family="sans-serif">{room.name}</text>')
            parts.append(f'<text x="{cx:.2f}" y="{cy + area_fs * 0.7:.2f}" '
                         f'text-anchor="middle" font-size="{area_fs}" '
                         f'fill="#64748b" font-family="sans-serif">{area:.1f}㎡</text>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.2f} {h:.2f}" '
            f'width="100%" height="100%">{"".join(parts)}</svg>')


def _label_center(polygon: list[Point2D], area_sqm: float) -> tuple[float, float]:
    """Compute the best label position inside a polygon.

    Strategy:
    1. Try bbox center — if inside polygon, use it.
    2. Try centroid (vertex average) — if inside, use it.
    3. Fall back to bbox center regardless (for convex rooms it always works).
    """
    if len(polygon) < 3:
        cx = sum(p.x for p in polygon) / max(1, len(polygon))
        cy = sum(p.y for p in polygon) / max(1, len(polygon))
        return cx, cy

    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    bbox_cx = (min(xs) + max(xs)) / 2
    bbox_cy = (min(ys) + max(ys)) / 2

    poly = [(p.x, p.y) for p in polygon]

    if _point_in_polygon(bbox_cx, bbox_cy, poly):
        return bbox_cx, bbox_cy

    # Try centroid
    cent_cx = sum(xs) / len(xs)
    cent_cy = sum(ys) / len(ys)
    if _point_in_polygon(cent_cx, cent_cy, poly):
        return cent_cx, cent_cy

    # Try weighted sample points inside the polygon
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    best_x, best_y, best_dist = bbox_cx, bbox_cy, 0
    steps = 5
    for si in range(steps):
        for sj in range(steps):
            tx = min_x + (max_x - min_x) * (si + 0.5) / steps
            ty = min_y + (max_y - min_y) * (sj + 0.5) / steps
            if _point_in_polygon(tx, ty, poly):
                dist = min(tx - min_x, max_x - tx, ty - min_y, max_y - ty)
                if dist > best_dist:
                    best_dist = dist
                    best_x, best_y = tx, ty

    return best_x, best_y


def _point_in_polygon(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
    """Ray casting algorithm."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside
