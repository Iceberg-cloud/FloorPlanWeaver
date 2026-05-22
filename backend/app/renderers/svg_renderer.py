"""Render LayoutDraft to SVG with Chinese labels, adaptive fonts, and precise centers."""

from __future__ import annotations

from app.schemas.layout import LayoutDraft, Point2D

_CJK_FONT = (
    "system-ui, -apple-system, 'Segoe UI', 'Microsoft YaHei', "
    "'PingFang SC', 'Noto Sans SC', sans-serif"
)


def render_layout_svg(layout: LayoutDraft) -> str:
    room_fill = {
        "客厅": "#dbeafe", "餐厅": "#fef3c7", "厨房": "#fce7f3",
        "主卧": "#dcfce7", "次卧": "#ede9fe", "卧室": "#dcfce7",
        "卫生间": "#cffafe", "阳台": "#f1f5f9", "书房": "#e0e7ff",
        "玄关": "#ffedd5", "儿童房": "#fef9c3", "主卫": "#cffafe",
        "客卫": "#cffafe", "客餐厅": "#dbeafe", "起居室": "#dbeafe",
    }
    room_stroke = {
        "客厅": "#3b82f6", "餐厅": "#f59e0b", "厨房": "#ec4899",
        "主卧": "#22c55e", "次卧": "#8b5cf6", "卧室": "#22c55e",
        "卫生间": "#06b6d4", "阳台": "#64748b", "书房": "#6366f1",
        "玄关": "#f97316", "儿童房": "#eab308", "主卫": "#06b6d4",
        "客卫": "#06b6d4", "客餐厅": "#3b82f6", "起居室": "#3b82f6",
    }

    all_pts: list[tuple[float, float]] = []
    if layout.outline_vertices:
        all_pts.extend((v.x, v.y) for v in layout.outline_vertices)
    for room in layout.rooms:
        for p in room.polygon:
            all_pts.append((p.x, p.y))

    pad = 0.8
    if all_pts:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        min_x, max_x = min(xs) - pad, max(xs) + pad
        min_y, max_y = min(ys) - pad, max(ys) + pad
    else:
        min_x, min_y = 0.0, 0.0
        max_x = float(layout.canvas.get("width", 10) or 10)
        max_y = float(layout.canvas.get("height", 8) or 8)

    vw = max(0.5, max_x - min_x)
    vh = max(0.5, max_y - min_y)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xml:lang="zh-CN" '
        f'viewBox="{min_x:.2f} {min_y:.2f} {vw:.2f} {vh:.2f}" width="100%" height="100%" '
        f'font-family="{_CJK_FONT}">',
    ]

    grid_step = 1.0
    gx0 = int(min_x)
    gx1 = int(max_x) + 1
    gy0 = int(min_y)
    gy1 = int(max_y) + 1
    for gx in range(gx0, gx1 + 1):
        parts.append(
            f'<line x1="{gx}" y1="{min_y:.2f}" x2="{gx}" y2="{max_y:.2f}" '
            f'stroke="#f1f5f9" stroke-width="0.03"/>'
        )
    for gy in range(gy0, gy1 + 1):
        parts.append(
            f'<line x1="{min_x:.2f}" y1="{gy}" x2="{max_x:.2f}" y2="{gy}" '
            f'stroke="#f1f5f9" stroke-width="0.03"/>'
        )

    if layout.outline_vertices:
        pts = " ".join(f"{v.x:.2f},{v.y:.2f}" for v in layout.outline_vertices)
        parts.append(
            f'<polygon points="{pts}" fill="rgba(148,163,184,0.05)" '
            f'stroke="#475569" stroke-width="0.1" stroke-linejoin="round"/>'
        )

    for room in layout.rooms:
        polygon = room.polygon
        if len(polygon) < 3:
            continue

        pts_str = " ".join(f"{p.x:.2f},{p.y:.2f}" for p in polygon)
        fill = room_fill.get(room.type, "#f5f5f5")
        stroke = room_stroke.get(room.type, "#94a3b8")
        cx, cy = _label_center(polygon, room.area_sqm)
        name_fs, area_fs, show_area, stroke_w = _label_font_sizes(polygon)
        clip_id = f"clip-{room.id}".replace(" ", "_")
        parts.append(f'<clipPath id="{clip_id}"><polygon points="{pts_str}"/></clipPath>')
        parts.append(
            f'<polygon points="{pts_str}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{stroke_w:.3f}" stroke-linejoin="miter"/>'
        )
        parts.append(
            f'<text x="{cx:.2f}" y="{cy - (name_fs * 0.45 if show_area else 0):.2f}" '
            f'text-anchor="middle" dominant-baseline="central" font-size="{name_fs:.3f}" '
            f'fill="#1e293b" font-weight="600" font-family="{_CJK_FONT}" '
            f'clip-path="url(#{clip_id})">{_escape_xml(room.name)}</text>'
        )
        if show_area and room.area_sqm > 0:
            parts.append(
                f'<text x="{cx:.2f}" y="{cy + name_fs * 0.42:.2f}" text-anchor="middle" '
                f'dominant-baseline="central" font-size="{area_fs:.3f}" '
                f'fill="#475569" font-family="{_CJK_FONT}" clip-path="url(#{clip_id})">'
                f"{room.area_sqm:.1f}㎡</text>"
            )

    parts.append("</svg>")
    return "".join(parts)


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _label_font_sizes(polygon: list[Point2D]) -> tuple[float, float, bool, float]:
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    w = max(0.35, max(xs) - min(xs))
    h = max(0.35, max(ys) - min(ys))
    short = min(w, h)
    long_side = max(w, h)
    name_fs = max(0.22, min(0.58, short * 0.48))
    area_fs = max(0.18, name_fs * 0.7)
    show_area = short >= 0.95 and long_side >= 1.35
    stroke_w = min(0.08, max(0.025, short * 0.05))
    return name_fs, area_fs, show_area, stroke_w


def _label_center(polygon: list[Point2D], area_sqm: float) -> tuple[float, float]:
    """Compute the best label position inside a polygon."""
    del area_sqm  # reserved for future area-based tuning
    if len(polygon) < 3:
        cx = sum(p.x for p in polygon) / max(1, len(polygon))
        cy = sum(p.y for p in polygon) / max(1, len(polygon))
        return cx, cy

    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    bbox_cx = (min_x + max_x) / 2
    bbox_cy = (min_y + max_y) / 2

    poly = [(p.x, p.y) for p in polygon]

    if _point_in_polygon(bbox_cx, bbox_cy, poly):
        return bbox_cx, bbox_cy

    cent_cx = sum(xs) / len(xs)
    cent_cy = sum(ys) / len(ys)
    if _point_in_polygon(cent_cx, cent_cy, poly):
        return cent_cx, cent_cy

    best_x, best_y, best_dist = bbox_cx, bbox_cy, -1.0
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
