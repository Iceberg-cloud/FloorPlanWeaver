"""Layout validation: boundary, overlap, area, adjacency checks."""

from app.schemas.layout import (
    LayoutDraft,
    LayoutValidationResult,
    SiteOutline,
)
from app.schemas.planner import PlannerFinalPlan


def validate_layout(
    layout: LayoutDraft,
    outline: SiteOutline | None,
    plan: PlannerFinalPlan | None,
) -> LayoutValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not layout.rooms:
        errors.append("布局中没有房间。")
        return LayoutValidationResult(
            hard_constraints_passed=False, errors=errors, warnings=warnings
        )

    # 1. Boundary check — all room vertices inside outline
    if outline and outline.vertices:
        if layout.compile_method not in ("grid", "grid_search"):
            outline_poly = [(v.x, v.y) for v in outline.vertices]
            for room in layout.rooms:
                for i, pt in enumerate(room.polygon):
                    if not _point_in_polygon(pt.x, pt.y, outline_poly):
                        errors.append(
                            f"房间「{room.name}」顶点 {i} ({pt.x:.1f},{pt.y:.1f}) 在轮廓外。"
                        )

    # 2. Overlap check — legacy grid skipped; grid_search uses boundary export
    if layout.compile_method == "grid_search":
        errors.extend(_grid_search_polygon_overlap_errors(layout.rooms))
    elif layout.compile_method != "grid":
        for i, r1 in enumerate(layout.rooms):
            for j in range(i + 1, len(layout.rooms)):
                r2 = layout.rooms[j]
                if _polygons_overlap(
                    [(p.x, p.y) for p in r1.polygon],
                    [(p.x, p.y) for p in r2.polygon],
                ):
                    errors.append(f"房间「{r1.name}」与「{r2.name}」重叠。")

    # 3. Total area check
    if outline and outline.total_area_sqm > 0:
        total_room_area = sum(r.area_sqm for r in layout.rooms)
        if total_room_area > outline.total_area_sqm * 1.05:
            errors.append(
                f"房间面积总和 {total_room_area:.1f}㎡ 超过轮廓面积 {outline.total_area_sqm:.1f}㎡ 的 105%。"
            )

    # 4. Area vs plan target check
    if plan:
        for item in plan.space_program:
            target = item.target_area_sqm
            if target and target > 0:
                matching = [r for r in layout.rooms if r.type == item.room_type or r.name == item.room_type]
                if matching:
                    actual = sum(r.area_sqm for r in matching) / len(matching)
                    deviation = abs(actual - target) / target
                    if deviation > 0.3:
                        warnings.append(
                            f"「{item.room_type}」面积 {actual:.1f}㎡ 与目标 {target:.1f}㎡ 偏差 {deviation:.0%}。"
                        )

    # 5. Adjacency check (soft)
    if plan:
        for rule in plan.adjacency_graph:
            if rule.relation != "required":
                continue
            src_rooms = [r for r in layout.rooms if r.name == rule.source or r.type == rule.source]
            tgt_rooms = [r for r in layout.rooms if r.name == rule.target or r.type == rule.target]
            if src_rooms and tgt_rooms:
                found = False
                for sr in src_rooms:
                    for tr in tgt_rooms:
                        if tr.id in sr.adjacent_to or sr.id in tr.adjacent_to:
                            found = True
                            break
                if not found:
                    warnings.append(
                        f"邻接要求「{rule.source}」与「{rule.target}」在布局中未体现。"
                    )

    return LayoutValidationResult(
        hard_constraints_passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


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


def _polygon_area_signed(poly: list[tuple[float, float]]) -> float:
    n = len(poly)
    area = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _polygon_area(poly: list[tuple[float, float]]) -> float:
    return abs(_polygon_area_signed(poly))


def _edge_intersection(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> tuple[float, float] | None:
    d1x = p2[0] - p1[0]
    d1y = p2[1] - p1[1]
    d2x = p4[0] - p3[0]
    d2y = p4[1] - p3[1]
    denom = d1x * d2y - d1y * d2x
    if abs(denom) < 1e-12:
        return None
    t = ((p3[0] - p1[0]) * d2y - (p3[1] - p1[1]) * d2x) / denom
    u = ((p3[0] - p1[0]) * d1y - (p3[1] - p1[1]) * d1x) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        return (p1[0] + t * d1x, p1[1] + t * d1y)
    return None


def _grid_search_polygon_overlap_errors(rooms) -> list[str]:
    """True overlap: one room's polygon contains another room's interior sample point."""
    from app.services.layout_geometry import point_in_polygon

    errors: list[str] = []
    if len(rooms) < 2:
        return errors

    def _sample_points(poly: list[tuple[float, float]], n: int = 5) -> list[tuple[float, float]]:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        pts: list[tuple[float, float]] = []
        for si in range(n):
            for sj in range(n):
                tx = min_x + (max_x - min_x) * (si + 0.5) / n
                ty = min_y + (max_y - min_y) * (sj + 0.5) / n
                if point_in_polygon(tx, ty, poly):
                    pts.append((tx, ty))
        return pts

    for i, r1 in enumerate(rooms):
        p1 = [(p.x, p.y) for p in r1.polygon]
        if len(p1) < 3:
            continue
        samples1 = _sample_points(p1)
        for j in range(i + 1, len(rooms)):
            r2 = rooms[j]
            p2 = [(p.x, p.y) for p in r2.polygon]
            if len(p2) < 3:
                continue
            for pt in samples1:
                if point_in_polygon(pt[0], pt[1], p2):
                    errors.append(
                        f"房间「{r1.name}」与「{r2.name}」导出图形重叠（网格单元不重叠，属显示多边形问题）。"
                    )
                    break
            else:
                for pt in _sample_points(p2):
                    if point_in_polygon(pt[0], pt[1], p1):
                        errors.append(
                            f"房间「{r1.name}」与「{r2.name}」导出图形重叠（网格单元不重叠，属显示多边形问题）。"
                        )
                        break
    return errors


def _polygons_overlap(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> bool:
    """Check if two polygons overlap (share interior area)."""
    n1 = len(poly1)
    n2 = len(poly2)
    for i in range(n1):
        for j in range(n2):
            if _edge_intersection(
                poly1[i], poly1[(i + 1) % n1],
                poly2[j], poly2[(j + 1) % n2],
            ):
                return True
    if _point_in_polygon(poly1[0][0], poly1[0][1], poly2):
        return True
    if _point_in_polygon(poly2[0][0], poly2[0][1], poly1):
        return True
    return False


def compute_outline_area(vertices: list[tuple[float, float]]) -> float:
    return _polygon_area(list(vertices))
