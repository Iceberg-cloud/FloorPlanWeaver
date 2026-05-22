"""Render LayoutDraft to SVG with Chinese labels."""
import base64
from app.schemas.layout import LayoutDraft


def render_layout_svg(layout: LayoutDraft) -> str:
    room_fill = {
        "客厅": "#e8f0fe", "餐厅": "#fef3e8", "厨房": "#fce8e6",
        "主卧": "#e6f4ea", "次卧": "#f3e8fd", "卫生间": "#e8f7fb",
        "阳台": "#f9f9f9", "书房": "#e8ecf0", "玄关": "#f5f0e8",
    }
    parts = []
    if layout.outline_vertices:
        pts = " ".join(f"{v.x:.2f},{v.y:.2f}" for v in layout.outline_vertices)
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#111" stroke-width="0.08" />')
    for room in layout.rooms:
        pts = " ".join(f"{p.x:.2f},{p.y:.2f}" for p in room.polygon)
        fill = room_fill.get(room.type, room_fill.get(room.name, "#f5f5f5"))
        parts.append(f'<polygon points="{pts}" fill="{fill}" stroke="#333" stroke-width="0.04" />')
        cx = sum(p.x for p in room.polygon) / len(room.polygon)
        cy = sum(p.y for p in room.polygon) / len(room.polygon)
        label = f"{room.name} {room.area_sqm}㎡"
        parts.append(f'<text x="{cx:.2f}" y="{cy:.2f}" text-anchor="middle" '
                     f'font-size="0.35" fill="#111" font-family="sans-serif">{label}</text>')
    w = layout.canvas.get("width", 10)
    h = layout.canvas.get("height", 8)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="100%" height="100%">{"".join(parts)}</svg>')
