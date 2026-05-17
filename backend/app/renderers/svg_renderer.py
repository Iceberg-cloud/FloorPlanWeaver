from app.schemas.drawer import DrawerDraft


def _points_to_str(points: list) -> str:
    return " ".join(f"{p.x},{p.y}" for p in points)


class SvgRenderer:
    def render(self, draft: DrawerDraft) -> str:
        width = draft.canvas.width
        height = draft.canvas.height
        room_fill = {
            "客厅": "#e8f0fe",
            "餐厅": "#fef3e8",
            "厨房": "#fce8e6",
            "主卧": "#e6f4ea",
            "次卧": "#f3e8fd",
            "卫生间": "#e8f7fb",
            "阳台": "#f9f9f9",
        }
        room_polygons = []
        labels = []
        for room in draft.rooms:
            points_str = _points_to_str(room.polygon)
            fill = room_fill.get(room.name, "#f5f5f5")
            room_polygons.append(
                f'<polygon points="{points_str}" fill="{fill}" stroke="#333" stroke-width="20" />'
            )
            cx = sum(p.x for p in room.polygon) / len(room.polygon)
            cy = sum(p.y for p in room.polygon) / len(room.polygon)
            labels.append(
                f'<text x="{cx}" y="{cy}" text-anchor="middle" font-size="260" fill="#111">{room.name}</text>'
            )

        outline = f'<polygon points="{_points_to_str(draft.outline)}" fill="none" stroke="#111" stroke-width="40" />'
        doors = [
            f'<line x1="{d.segment[0].x}" y1="{d.segment[0].y}" x2="{d.segment[1].x}" y2="{d.segment[1].y}" stroke="#0f766e" stroke-width="60" />'
            for d in draft.doors
        ]
        windows = [
            f'<line x1="{w.wall_segment[0].x}" y1="{w.wall_segment[0].y}" x2="{w.wall_segment[1].x}" y2="{w.wall_segment[1].y}" stroke="#2563eb" stroke-width="60" />'
            for w in draft.windows
        ]

        parts = [outline, *room_polygons, *doors, *windows, *labels]
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="100%" height="100%">{"".join(parts)}</svg>'
        )
