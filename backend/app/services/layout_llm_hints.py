"""Map LLM normalized position/size hints to compiler geometry."""

from __future__ import annotations

from app.services.layout_grid import CELL_SIZE

_CORNERS = ("BL", "BR", "TL", "TR")


def corner_from_normalized_center(center_x: float, center_y: float) -> str:
    """Pick outline corner anchor closest to normalized center (0–1)."""
    cx = max(0.0, min(1.0, center_x))
    cy = max(0.0, min(1.0, center_y))
    best = _CORNERS[0]
    best_d = float("inf")
    for name, (px, py) in (("BL", (0.0, 0.0)), ("BR", (1.0, 0.0)), ("TL", (0.0, 1.0)), ("TR", (1.0, 1.0))):
        d = (cx - px) ** 2 + (cy - py) ** 2
        if d < best_d:
            best_d = d
            best = name
    return best


def world_center_from_normalized(
    center_x: float,
    center_y: float,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> tuple[float, float]:
    w = max_x - min_x
    h = max_y - min_y
    return (min_x + max(0.0, min(1.0, center_x)) * w, min_y + max(0.0, min(1.0, center_y)) * h)


def target_area_from_hint(
    planner_area: float,
    width_ratio: float | None,
    height_ratio: float | None,
    bbox_area: float,
    *,
    blend: float = 0.55,
) -> float:
    """Blend planner target area with LLM bbox-fraction estimate."""
    if not width_ratio or not height_ratio or bbox_area <= 0:
        return planner_area
    hinted = max(1.0, width_ratio * height_ratio * bbox_area)
    return max(1.0, planner_area * (1.0 - blend) + hinted * blend)


def sort_corners_by_hint(
    candidates: list[str],
    center_x: float | None,
    center_y: float | None,
) -> list[str]:
    if center_x is None or center_y is None:
        return candidates
    preferred = corner_from_normalized_center(center_x, center_y)
    ordered = [preferred] + [c for c in candidates if c != preferred]
    for c in candidates:
        if c not in ordered:
            ordered.append(c)
    return ordered


def sort_cells_by_world_center(
    cells: list[tuple[int, int]],
    grid,
    wx: float,
    wy: float,
) -> list[tuple[int, int]]:
    def dist(c: tuple[int, int]) -> float:
        i, j = c
        cx = grid.origin_x + (i + 0.5) * CELL_SIZE
        cy = grid.origin_y + (j + 0.5) * CELL_SIZE
        return (cx - wx) ** 2 + (cy - wy) ** 2

    return sorted(cells, key=dist)
