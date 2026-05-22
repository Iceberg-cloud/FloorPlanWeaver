"""Geometry helpers for layout packing and post-processing."""

from __future__ import annotations

import hashlib

from app.schemas.layout import LayoutRoom, Point2D


def polygon_area(vertices: list[tuple[float, float]]) -> float:
    n = len(vertices)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def point_in_polygon(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
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


def rect_from_points(polygon: list[Point2D]) -> tuple[float, float, float, float]:
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def rect_to_polygon(x0: float, y0: float, x1: float, y1: float) -> list[Point2D]:
    return [
        Point2D(x=x0, y=y0),
        Point2D(x=x1, y=y0),
        Point2D(x=x1, y=y1),
        Point2D(x=x0, y=y1),
    ]


def rect_area(x0: float, y0: float, x1: float, y1: float) -> float:
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def update_room_rect(
    room: LayoutRoom, x0: float, y0: float, x1: float, y1: float,
) -> LayoutRoom:
    return room.model_copy(
        update={
            "polygon": rect_to_polygon(x0, y0, x1, y1),
            "area_sqm": round(rect_area(x0, y0, x1, y1), 1),
        }
    )


def rects_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    gap: float = 0.05,
) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + gap <= bx0 or bx1 + gap <= ax0 or ay1 + gap <= by0 or by1 + gap <= ay0)


def rect_corners_inside(px0: float, py0: float, px1: float, py1: float, poly: list[tuple[float, float]]) -> bool:
    corners = [(px0, py0), (px1, py0), (px1, py1), (px0, py1)]
    return all(point_in_polygon(x, y, poly) for x, y in corners)


def shrink_rect_into_polygon(
    x0: float, y0: float, x1: float, y1: float,
    poly: list[tuple[float, float]], *, min_side: float = 0.4, max_iter: int = 40, seed: int = 0,
) -> tuple[float, float, float, float]:
    if rect_corners_inside(x0, y0, x1, y1, poly):
        return x0, y0, x1, y1
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    w = max(x1 - x0, min_side)
    h = max(y1 - y0, min_side)
    for _ in range(max_iter):
        scale = 1.0
        for step in range(max_iter):
            scale *= 0.92
            hw = w * scale / 2
            hh = h * scale / 2
            nx0, ny0 = cx - hw, cy - hh
            nx1, ny1 = cx + hw, cy + hh
            if hw < min_side / 2 or hh < min_side / 2:
                break
            if rect_corners_inside(nx0, ny0, nx1, ny1, poly):
                return nx0, ny0, nx1, ny1
    for delta in (0.5, 1.0, 1.5, 2.0):
        if point_in_polygon(cx, cy, poly):
            return cx - delta, cy - delta, cx + delta, cy + delta
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    return cx - 0.6, cy - 0.6, cx + 0.6, cy + 0.6


def bbox_of_polygon(poly: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _find_interior_point(
    poly: list[tuple[float, float]], *, seed: int = 0,
) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = bbox_of_polygon(poly)
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    if point_in_polygon(cx, cy, poly):
        return cx, cy
    import random
    rng = random.Random(seed)
    for _ in range(200):
        x = min_x + (max_x - min_x) * rng.random()
        y = min_y + (max_y - min_y) * rng.random()
        if point_in_polygon(x, y, poly):
            return x, y
    n = len(poly)
    for i in range(n):
        mx = (poly[i][0] + poly[(i + 1) % n][0]) / 2
        my = (poly[i][1] + poly[(i + 1) % n][1]) / 2
        if point_in_polygon(mx, my, poly):
            return mx, my
    return cx, cy


def stable_room_seed(name: str) -> int:
    h = hashlib.md5(name.encode()).hexdigest()
    return int(h[:8], 16) & 0x7FFFFFFF
