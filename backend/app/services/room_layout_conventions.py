"""Common residential adjacency / zoning conventions for Method A grid search.

References: public–private zoning, kitchen–dining adjacency, wet-core clustering,
bedrooms on quiet exterior walls, balcony on living side (south in CN layouts).
"""

from __future__ import annotations

# Prefer sharing an edge (soft)
PREFER_ADJACENT: list[tuple[str, str]] = [
    ("厨房", "餐厅"),
    ("餐厅", "客厅"),
    ("客餐厅", "厨房"),
    ("客餐厅", "餐厅"),
    ("客厅", "阳台"),
    ("客厅", "餐厅"),
    ("主卧", "主卫"),
    ("主卧", "卫生间"),
    ("次卧", "卫生间"),
    ("卧室", "卫生间"),
]

# Discourage sharing an edge (soft)
AVOID_ADJACENT: list[tuple[str, str]] = [
    ("厨房", "主卧"),
    ("厨房", "次卧"),
    ("厨房", "卧室"),
    ("厨房", "儿童房"),
    ("卫生间", "厨房"),
    ("阳台", "厨房"),
    ("卫生间", "客厅"),
]

DEFAULT_PREFER_EDGE: dict[str, str] = {
    "阳台": "south",
    "客厅": "south",
    "餐厅": "south",
    "起居室": "south",
    "客餐厅": "south",
    "厨房": "west",
    "卫生间": "north",
    "主卫": "north",
    "客卫": "north",
    "主卧": "north",
    "次卧": "north",
    "卧室": "north",
    "儿童房": "north",
    "书房": "north",
}

DEFAULT_ZONE: dict[str, str] = {
    "阳台": "south",
    "客厅": "south",
    "餐厅": "south",
    "起居室": "south",
    "客餐厅": "south",
    "厨房": "west",
    "玄关": "near_entrance",
    "卫生间": "north",
    "主卫": "north",
    "客卫": "north",
    "主卧": "north",
    "次卧": "north",
    "卧室": "north",
    "儿童房": "north",
    "书房": "north",
}

# Typical usable areas & short-side hints (GB 50096-2011 / common practice, meters)
# Format: (min_area_sqm, typical_short_side_m, aspect_min, aspect_max)
ROOM_TYPICAL_SIZE: dict[str, tuple[float, float, float, float]] = {
    "客厅": (10.0, 3.0, 0.55, 2.4),
    "餐厅": (8.0, 2.4, 0.45, 2.2),
    "客餐厅": (12.0, 3.0, 0.55, 2.5),
    "起居室": (10.0, 3.0, 0.55, 2.4),
    "主卧": (9.0, 2.8, 0.45, 2.2),
    "次卧": (5.0, 2.2, 0.4, 2.0),
    "卧室": (5.0, 2.2, 0.4, 2.0),
    "儿童房": (5.0, 2.2, 0.4, 2.0),
    "书房": (6.0, 2.2, 0.4, 2.0),
    "厨房": (4.0, 1.6, 0.35, 2.5),
    "卫生间": (2.5, 1.4, 0.25, 2.8),
    "主卫": (3.0, 1.5, 0.25, 2.8),
    "客卫": (2.5, 1.4, 0.25, 2.8),
    "阳台": (3.0, 1.2, 0.15, 4.0),
}

# Minimum target areas (㎡) to avoid unusably thin strips in SVG
MIN_TARGET_AREA_SQM: dict[str, float] = {
    "客厅": 12.0,
    "餐厅": 8.0,
    "客餐厅": 14.0,
    "起居室": 12.0,
    "主卧": 10.0,
    "次卧": 8.0,
    "卧室": 8.0,
    "厨房": 5.0,
    "卫生间": 3.5,
    "主卫": 4.0,
    "客卫": 3.5,
    "阳台": 3.0,
    "书房": 6.0,
    "儿童房": 8.0,
}

# Default strip band order (north → south rows in horizontal strip layout)
BAND_ROW_SERVICE = ["卫生间", "主卫", "客卫", "洗手间", "厨房"]
BAND_ROW_PRIVATE = ["主卧", "次卧", "卧室", "儿童房", "书房"]
BAND_ROW_PUBLIC_EDGE = ["阳台"]


def _base_type(label: str) -> str:
    if label and label[-1].isdigit():
        i = len(label) - 1
        while i > 0 and label[i - 1].isdigit():
            i -= 1
        return label[:i]
    return label


def min_target_area(room_type: str) -> float:
    if room_type in ROOM_TYPICAL_SIZE:
        return max(MIN_TARGET_AREA_SQM.get(room_type, 3.0), ROOM_TYPICAL_SIZE[room_type][0])
    return MIN_TARGET_AREA_SQM.get(room_type, 3.0)


def typical_aspect_bounds(room_type: str) -> tuple[float, float]:
    if room_type in ROOM_TYPICAL_SIZE:
        return ROOM_TYPICAL_SIZE[room_type][2], ROOM_TYPICAL_SIZE[room_type][3]
    return 0.35, 3.0


def merge_near_lists(existing: list[str], room_type: str) -> list[str]:
    out = list(existing or [])
    for a, b in PREFER_ADJACENT:
        if a == room_type and b not in out:
            out.append(b)
        elif b == room_type and a not in out:
            out.append(a)
    return out


def merge_avoid_lists(existing: list[str], room_type: str) -> list[str]:
    out = list(existing or [])
    for a, b in AVOID_ADJACENT:
        if a == room_type and b not in out:
            out.append(b)
        elif b == room_type and a not in out:
            out.append(a)
    return out


def prefer_edge_for(room_type: str, current: str = "") -> str:
    if current:
        return current
    return DEFAULT_PREFER_EDGE.get(room_type, "")


def zone_for(room_type: str, current: str = "") -> str:
    if current and current not in ("center", "flexible"):
        return current
    return DEFAULT_ZONE.get(room_type, "center")


def convention_adjacency_score(
    state,
    grid,
    constraint,
    cells: list[tuple[int, int]],
    name_to_type: dict[str, str] | None = None,
) -> float:
    """Bonus/penalty from standard residential adjacency when placing `constraint`."""
    score = 0.0
    rt = constraint.room_type
    for i, j in cells:
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if not (0 <= ni < grid.cols and 0 <= nj < grid.rows):
                continue
            oid = state.rid[nj][ni]
            if oid <= 0:
                continue
            other_name = state.room_names.get(oid, "")
            other_rt = (name_to_type or {}).get(other_name) or _base_type(other_name)
            if not other_rt:
                other_rt = _base_type(other_name)
            for a, b in PREFER_ADJACENT:
                if (rt == a and other_rt == b) or (rt == b and other_rt == a):
                    score += 5.0
            for a, b in AVOID_ADJACENT:
                if (rt == a and other_rt == b) or (rt == b and other_rt == a):
                    score -= 8.0
    return score


def build_default_bands(
    public_types: list[str],
    private_types: list[str],
    service_types: list[str],
) -> list[list[str]]:
    """North (quiet/private) → service wet core → south edge (balcony)."""
    row_private: list[str] = []
    for key in BAND_ROW_PRIVATE:
        if key in private_types and key not in row_private:
            row_private.append(key)
    for r in private_types:
        if r not in row_private and r not in ("厨房", "客厅", "餐厅", "客餐厅", "阳台"):
            row_private.append(r)

    row_service: list[str] = []
    for key in BAND_ROW_SERVICE:
        if key in service_types or key in public_types:
            if key not in row_service:
                row_service.append(key)
    if "厨房" not in row_service and "厨房" in public_types + service_types + private_types:
        row_service.append("厨房")

    row_edge: list[str] = []
    for key in BAND_ROW_PUBLIC_EDGE:
        if key in public_types and key not in row_edge:
            row_edge.append(key)

    bands: list[list[str]] = []
    if row_private:
        bands.append(row_private)
    if row_service:
        bands.append(row_service)
    if row_edge:
        bands.append(row_edge)
    return bands
