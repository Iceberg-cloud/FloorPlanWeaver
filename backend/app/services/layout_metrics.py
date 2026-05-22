"""Area coverage metrics for Method A vector layouts."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.layout import LayoutDraft, LayoutRoom, SiteOutline
from app.services.layout_geometry import polygon_area


@dataclass
class LayoutAreaMetrics:
    outline_area_sqm: float
    planned_area_sqm: float
    area_coverage_ratio: float
    room_count: int
    per_room: list[dict]

    def summary_line(self) -> str:
        return (
            f"规划面积 {self.planned_area_sqm:.1f}㎡ / 外轮廓 {self.outline_area_sqm:.1f}㎡ "
            f"（占比 {self.area_coverage_ratio:.1%}）"
        )


def outline_area_sqm(outline: SiteOutline) -> float:
    if outline.total_area_sqm and outline.total_area_sqm > 0:
        return float(outline.total_area_sqm)
    if len(outline.vertices) >= 3:
        poly = [(v.x, v.y) for v in outline.vertices]
        return polygon_area(poly)
    bb = outline.bounding_box or {}
    w = float(bb.get("width") or 0)
    h = float(bb.get("height") or 0)
    return w * h if w > 0 and h > 0 else 0.0


def room_polygon_area(room: LayoutRoom) -> float:
    if room.area_sqm and room.area_sqm > 0:
        return float(room.area_sqm)
    if len(room.polygon) >= 3:
        return polygon_area([(p.x, p.y) for p in room.polygon])
    return 0.0


def compute_layout_area_metrics(
    layout: LayoutDraft,
    outline: SiteOutline,
) -> LayoutAreaMetrics:
    outline_sqm = outline_area_sqm(outline)
    per_room: list[dict] = []
    planned = 0.0
    for room in layout.rooms or []:
        area = room_polygon_area(room)
        planned += area
        share = (area / outline_sqm) if outline_sqm > 0 else 0.0
        per_room.append({
            "name": room.name,
            "room_type": room.type,
            "area_sqm": round(area, 2),
            "share_of_outline": round(share, 4),
        })
    ratio = (planned / outline_sqm) if outline_sqm > 0 else 0.0
    return LayoutAreaMetrics(
        outline_area_sqm=round(outline_sqm, 2),
        planned_area_sqm=round(planned, 2),
        area_coverage_ratio=round(ratio, 4),
        room_count=len(layout.rooms or []),
        per_room=per_room,
    )
