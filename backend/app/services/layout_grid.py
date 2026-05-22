"""Discrete 0.25m grid inside site outline — source of truth for grid layout."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable

from app.schemas.layout import LayoutRoom, Point2D
from app.services.layout_geometry import point_in_polygon

CELL_SIZE = 0.25
CELL_AREA = CELL_SIZE * CELL_SIZE


@dataclass
class GridMap:
    origin_x: float
    origin_y: float
    cols: int
    rows: int
    inside: list[list[bool]]
    rid: list[list[int]] = field(default_factory=list)
    room_names: dict[int, str] = field(default_factory=dict)
    _next_rid: int = 1

    @classmethod
    def from_outline(
        cls,
        poly: list[tuple[float, float]],
        *,
        cell_size: float = CELL_SIZE,
    ) -> GridMap:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        cols = max(1, int(math.ceil((max_x - min_x) / cell_size)))
        rows = max(1, int(math.ceil((max_y - min_y) / cell_size)))
        inside: list[list[bool]] = []
        for j in range(rows):
            row: list[bool] = []
            cy = min_y + (j + 0.5) * cell_size
            for i in range(cols):
                cx = min_x + (i + 0.5) * cell_size
                row.append(point_in_polygon(cx, cy, poly))
            inside.append(row)
        g = cls(
            origin_x=min_x,
            origin_y=min_y,
            cols=cols,
            rows=rows,
            inside=inside,
        )
        g.rid = [[0] * cols for _ in range(rows)]
        return g

    @staticmethod
    def target_cells(target_area_sqm: float) -> int:
        return max(1, int(round(target_area_sqm / CELL_AREA)))

    def total_inside(self) -> int:
        return sum(1 for j in range(self.rows) for i in range(self.cols) if self.inside[j][i])

    def count_free_inside(self) -> int:
        return sum(
            1
            for j in range(self.rows)
            for i in range(self.cols)
            if self.inside[j][i] and self.rid[j][i] == 0
        )

    def count_room(self, room_id: int) -> int:
        return sum(
            1
            for j in range(self.rows)
            for i in range(self.cols)
            if self.inside[j][i] and self.rid[j][i] == room_id
        )

    def register_room(self, name: str) -> int:
        rid = self._next_rid
        self._next_rid += 1
        self.room_names[rid] = name
        return rid

    def zone_cell_bounds(
        self,
        entrance_side: str,
        zone: str,
        ratio: float = 0.48,
    ) -> tuple[int, int, int, int]:
        """Inclusive min i/j, exclusive max i/j in cell indices."""
        split_i = int(self.cols * ratio)
        split_j = int(self.rows * ratio)
        if entrance_side == "bottom":
            if zone == "front":
                return (0, 0, self.cols, max(1, split_j))
            return (0, split_j, self.cols, self.rows)
        if entrance_side == "top":
            if zone == "front":
                return (0, self.rows - max(1, split_j), self.cols, self.rows)
            return (0, 0, self.cols, self.rows - split_j)
        if entrance_side == "left":
            if zone == "front":
                return (0, 0, max(1, split_i), self.rows)
            return (split_i, 0, self.cols, self.rows)
        if zone == "front":
            return (self.cols - max(1, split_i), 0, self.cols, self.rows)
        return (0, 0, split_i, self.rows)

    def cell_zone_at(
        self, i: int, j: int, entrance_side: str, ratio: float = 0.48
    ) -> str:
        split_i = int(self.cols * ratio)
        split_j = int(self.rows * ratio)
        if entrance_side == "bottom":
            return "front" if j < split_j else "back"
        if entrance_side == "top":
            return "front" if j >= self.rows - split_j else "back"
        if entrance_side == "left":
            return "front" if i < split_i else "back"
        return "front" if i >= self.cols - split_i else "back"

    def _corner_origin(
        self,
        corner: str,
        zb: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        i0, j0, i1, j1 = zb
        if corner == "BL":
            return i0, j0, 1, 1
        if corner == "BR":
            return i1 - 1, j0, -1, 1
        if corner == "TL":
            return i0, j1 - 1, 1, -1
        return i1 - 1, j1 - 1, -1, -1

    def _iter_rect_cells(
        self,
        ai: int, aj: int, wi: int, hj: int, di: int, dj: int,
    ) -> list[tuple[int, int]]:
        cells: list[tuple[int, int]] = []
        for a in range(wi):
            for b in range(hj):
                i = ai + di * a if di > 0 else ai - a
                j = aj + dj * b if dj > 0 else aj - b
                if 0 <= i < self.cols and 0 <= j < self.rows:
                    cells.append((i, j))
        return cells

    def _can_claim(self, cells: list[tuple[int, int]], room_id: int) -> bool:
        for i, j in cells:
            if not self.inside[j][i] or (self.rid[j][i] != 0 and self.rid[j][i] != room_id):
                return False
        return bool(cells)

    def _claim(self, cells: list[tuple[int, int]], room_id: int) -> None:
        for i, j in cells:
            self.rid[j][i] = room_id

    def place_rect_room(
        self,
        room_id: int,
        corner: str,
        zone: str,
        entrance_side: str,
        target_cells: int,
        *,
        allow_notch: bool = True,
        zone_bounds: tuple[int, int, int, int] | None = None,
    ) -> bool:
        zb = zone_bounds or self.zone_cell_bounds(entrance_side, zone)
        ai, aj, di, dj = self._corner_origin(corner, zb)
        aspect = 1.4 if target_cells > 24 else 1.2
        wi = max(2, int(math.sqrt(target_cells * aspect)))
        hj = max(2, (target_cells + wi - 1) // wi)
        i0, j0, i1, j1 = zb
        max_wi = max(1, i1 - i0)
        max_hj = max(1, j1 - j0)
        wi = min(wi, max_wi)
        hj = min(hj, max_hj)

        for _ in range(80):
            cells = self._iter_rect_cells(ai, aj, wi, hj, di, dj)
            if len(cells) >= target_cells and self._can_claim(cells, room_id):
                self._claim(cells, room_id)
                return True
            if len(cells) < target_cells:
                grown = False
                if wi < max_wi:
                    wi += 1
                    grown = True
                elif hj < max_hj:
                    hj += 1
                    grown = True
                if not grown:
                    break
            else:
                if wi > 2 and wi >= hj:
                    wi -= 1
                elif hj > 2:
                    hj -= 1
                else:
                    break

        cells = self._iter_rect_cells(ai, aj, wi, hj, di, dj)
        if cells and self._can_claim(cells, room_id):
            self._claim(cells, room_id)
            if allow_notch and self.count_room(room_id) < target_cells:
                self._add_one_notch(room_id, set(cells), zb)
            return True
        return False

    def _add_one_notch(
        self,
        room_id: int,
        base_set: set[tuple[int, int]],
        zb: tuple[int, int, int, int],
    ) -> None:
        i0, j0, i1, j1 = zb
        candidates: list[tuple[int, int]] = []
        for i in range(i0, i1):
            for j in range(j0, j1):
                if (i, j) in base_set:
                    continue
                if not self.inside[j][i] or self.rid[j][i] != 0:
                    continue
                for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                    if (ni, nj) in base_set:
                        candidates.append((i, j))
                        break
        if candidates:
            i, j = candidates[0]
            self.rid[j][i] = room_id

    def claim_free_in_zone(
        self,
        room_id: int,
        zone: str,
        entrance_side: str,
        count: int,
        *,
        zone_bounds: tuple[int, int, int, int] | None = None,
    ) -> bool:
        zb = zone_bounds or self.zone_cell_bounds(entrance_side, zone)
        i0, j0, i1, j1 = zb
        claimed = 0
        for j in range(j0, j1):
            for i in range(i0, i1):
                if claimed >= count:
                    return True
                if self.inside[j][i] and self.rid[j][i] == 0:
                    self.rid[j][i] = room_id
                    claimed += 1
        return claimed > 0

    def free_cells_in_zone(
        self, entrance_side: str, zone: str
    ) -> list[tuple[int, int]]:
        zb = self.zone_cell_bounds(entrance_side, zone)
        return self.free_cells_in_bounds(zb, entrance_side=entrance_side)

    def free_cells_in_bounds(
        self,
        bounds: tuple[int, int, int, int],
        *,
        entrance_side: str = "bottom",
        prefer_low_y: bool = False,
    ) -> list[tuple[int, int]]:
        i0, j0, i1, j1 = bounds
        cells: list[tuple[int, int]] = []
        for j in range(j0, j1):
            for i in range(i0, i1):
                if self.inside[j][i] and self.rid[j][i] == 0:
                    cells.append((i, j))
        if prefer_low_y or entrance_side == "bottom":
            cells.sort(key=lambda c: (c[1], c[0]))
        elif entrance_side == "top":
            cells.sort(key=lambda c: (-c[1], c[0]))
        else:
            cells.sort(key=lambda c: (c[0], c[1]))
        return cells

    def free_cells_sorted(
        self,
        entrance_side: str,
        *,
        zone: str | None = None,
        prefer_low_y: bool = False,
    ) -> list[tuple[int, int]]:
        zb = self.zone_cell_bounds(entrance_side, zone) if zone else (0, 0, self.cols, self.rows)
        return self.free_cells_in_bounds(zb, entrance_side=entrance_side, prefer_low_y=prefer_low_y)

    def bfs_claim(
        self,
        room_id: int,
        seed: tuple[int, int],
        count: int,
        zone_bounds: tuple[int, int, int, int] | None = None,
    ) -> int:
        si, sj = seed
        if not (0 <= si < self.cols and 0 <= sj < self.rows):
            return 0
        if not self.inside[sj][si] or self.rid[sj][si] != 0:
            return 0
        i0, j0, i1, j1 = zone_bounds or (0, 0, self.cols, self.rows)
        visited: set[tuple[int, int]] = set()
        queue: deque[tuple[int, int]] = deque()
        queue.append((si, sj))
        visited.add((si, sj))
        claimed = 0
        while queue and claimed < count:
            i, j = queue.popleft()
            if not self.inside[j][i] or self.rid[j][i] != 0:
                continue
            if not (i0 <= i < i1 and j0 <= j < j1):
                continue
            self.rid[j][i] = room_id
            claimed += 1
            for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= ni < self.cols and 0 <= nj < self.rows and (ni, nj) not in visited:
                    visited.add((ni, nj))
                    queue.append((ni, nj))
        return claimed

    def fill_all_free(
        self,
        room_priority: list[int],
        entrance_side: str = "bottom",
        room_zones: dict[int, str] | None = None,
        room_caps: dict[int, int] | None = None,
    ) -> None:
        def zone_key(i: int, j: int) -> str:
            return self.cell_zone_at(i, j, entrance_side)
        self.fill_all_free_zoned(room_priority, room_zones or {}, room_caps, zone_key)

    def fill_all_free_zoned(
        self,
        room_priority: list[int],
        room_zones: dict[int, str] | None,
        room_caps: dict[int, int] | None,
        cell_zone_fn: Callable[[int, int], str],
    ) -> None:
        rid_to_cells: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for j in range(self.rows):
            for i in range(self.cols):
                if self.rid[j][i] > 0:
                    rid_to_cells[self.rid[j][i]].append((i, j))

        for j in range(self.rows):
            for i in range(self.cols):
                if not self.inside[j][i] or self.rid[j][i] != 0:
                    continue
                cz = cell_zone_fn(i, j)
                best_rid = 0
                best_d = 10**9
                for rid in room_priority:
                    rz = (room_zones or {}).get(rid, "")
                    if rz and rz != cz:
                        continue
                    cap = (room_caps or {}).get(rid)
                    if cap is not None and len(rid_to_cells.get(rid, [])) >= cap:
                        continue
                    for bi, bj in rid_to_cells.get(rid, []):
                        d = abs(i - bi) + abs(j - bj)
                        if d < best_d:
                            best_d = d
                            best_rid = rid
                if best_rid:
                    self.rid[j][i] = best_rid
                    rid_to_cells[best_rid].append((i, j))

    def force_fill_remaining(
        self,
        room_priority: list[int],
        *,
        prefer_living_last: bool | None = None,
    ) -> int:
        """Assign every interior cell still empty; prefer last ids in priority (living/dining)."""
        if not room_priority:
            return 0
        rid_to_cells: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for j in range(self.rows):
            for i in range(self.cols):
                if self.rid[j][i] > 0:
                    rid_to_cells[self.rid[j][i]].append((i, j))

        filled = 0
        for j in range(self.rows):
            for i in range(self.cols):
                if not self.inside[j][i] or self.rid[j][i] != 0:
                    continue
                best_rid = 0
                best_d = 10**9
                search = list(reversed(room_priority)) if prefer_living_last else room_priority
                for rid in search:
                    cells = rid_to_cells.get(rid, [])
                    if not cells:
                        continue
                    for bi, bj in cells:
                        d = abs(i - bi) + abs(j - bj)
                        if d < best_d:
                            best_d = d
                            best_rid = rid
                if not best_rid:
                    best_rid = room_priority[-1]
                self.rid[j][i] = best_rid
                rid_to_cells[best_rid].append((i, j))
                filled += 1
        return filled

    def cells_are_single_rect(self, room_id: int) -> bool:
        cells = [
            (i, j)
            for j in range(self.rows)
            for i in range(self.cols)
            if self.inside[j][i] and self.rid[j][i] == room_id
        ]
        if not cells:
            return False
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        i0, i1 = min(xs), max(xs)
        j0, j1 = min(ys), max(ys)
        expected = (i1 - i0 + 1) * (j1 - j0 + 1)
        return len(cells) == expected

    def cells_to_boundary_polygon(self, room_id: int) -> list[tuple[float, float]]:
        """Outer boundary of rectilinear cell union (CCW), for L/T-shaped rooms."""
        cells = set()
        for j in range(self.rows):
            for i in range(self.cols):
                if self.inside[j][i] and self.rid[j][i] == room_id:
                    cells.add((i, j))
        if not cells:
            return []

        edge_set: set[tuple[tuple[float, float], tuple[float, float]]] = set()
        for i, j in cells:
            x0 = self.origin_x + i * CELL_SIZE
            y0 = self.origin_y + j * CELL_SIZE
            x1 = x0 + CELL_SIZE
            y1 = y0 + CELL_SIZE
            sides = [
                ((_point_key(x0, y0), _point_key(x1, y0)), (i, j - 1)),  # bottom
                ((_point_key(x1, y0), _point_key(x1, y1)), (i + 1, j)),  # right
                ((_point_key(x0, y1), _point_key(x1, y1)), (i, j + 1)),  # top
                ((_point_key(x0, y0), _point_key(x0, y1)), (i - 1, j)),  # left
            ]
            for (a, b), (ni, nj) in sides:
                if (ni, nj) not in cells:
                    edge_set.add(_edge_key(a, b))

        if not edge_set:
            return []

        adj: dict[tuple[float, float], list[tuple[float, float]]] = defaultdict(list)
        for a, b in edge_set:
            adj[a].append(b)
            adj[b].append(a)

        verts = list(adj.keys())
        if len(verts) < 3:
            return _dedupe_polygon(verts)

        start = min(verts, key=lambda p: (p[1], p[0]))
        virtual_prev = (start[0], start[1] - CELL_SIZE)
        polygon: list[tuple[float, float]] = [start]
        prev = virtual_prev
        current = start
        guard = 0
        while guard < len(edge_set) * 4 + 8:
            guard += 1
            nxt = _pick_boundary_next(prev, current, adj[current])
            if nxt is None:
                break
            if nxt == start and len(polygon) >= 3:
                break
            if nxt != start:
                polygon.append(nxt)
            prev, current = current, nxt
            if current == start:
                break

        return _dedupe_polygon(polygon)

    def cells_to_bbox_polygon(self, room_id: int) -> list[tuple[float, float]]:
        xs: list[int] = []
        ys: list[int] = []
        for j in range(self.rows):
            for i in range(self.cols):
                if self.inside[j][i] and self.rid[j][i] == room_id:
                    xs.append(i)
                    ys.append(j)
        if not xs:
            return []
        ox, oy = self.origin_x, self.origin_y
        cs = CELL_SIZE
        i0, i1 = min(xs), max(xs) + 1
        j0, j1 = min(ys), max(ys) + 1
        return [
            (ox + i0 * cs, oy + j0 * cs),
            (ox + i1 * cs, oy + j0 * cs),
            (ox + i1 * cs, oy + j1 * cs),
            (ox + i0 * cs, oy + j1 * cs),
        ]

    def cells_to_polygon(self, room_id: int) -> list[tuple[float, float]]:
        """Deprecated scanline merge; use boundary trace for non-convex rectilinear shapes."""
        if self.cells_are_single_rect(room_id):
            return self.cells_to_bbox_polygon(room_id)
        pts = self.cells_to_boundary_polygon(room_id)
        if len(pts) >= 3:
            return pts
        return self.cells_to_bbox_polygon(room_id)

    def assign_cells_to_room(
        self,
        room_id: int,
        cells: list[tuple[int, int]],
        count: int,
    ) -> None:
        n = 0
        for i, j in cells:
            if n >= count:
                break
            if self.inside[j][i] and self.rid[j][i] == 0:
                self.rid[j][i] = room_id
                n += 1

    def balance_toward_targets(
        self,
        room_targets: dict[int, int],
        *,
        max_passes: int = 12,
    ) -> None:
        for _ in range(max_passes):
            changed = False
            for rid, target in room_targets.items():
                cur = self.count_room(rid)
                if cur == target:
                    continue
                if cur < target:
                    if self._grow_room_by_one(rid):
                        changed = True
                elif cur > target and self._shrink_room_by_one(rid):
                    changed = True
            if not changed:
                break

    def _grow_room_by_one(self, room_id: int) -> bool:
        for j in range(self.rows):
            for i in range(self.cols):
                if self.rid[j][i] != room_id:
                    continue
                for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                    if 0 <= ni < self.cols and 0 <= nj < self.rows:
                        if self.inside[nj][ni] and self.rid[nj][ni] == 0:
                            self.rid[nj][ni] = room_id
                            return True
        return False

    def _shrink_room_by_one(self, room_id: int) -> bool:
        border: list[tuple[int, int]] = []
        for j in range(self.rows):
            for i in range(self.cols):
                if self.rid[j][i] != room_id:
                    continue
                neighbors = sum(
                    1
                    for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1))
                    if 0 <= ni < self.cols
                    and 0 <= nj < self.rows
                    and self.rid[nj][ni] != room_id
                )
                if neighbors > 0:
                    border.append((i, j))
        if len(border) <= 2:
            return False
        i, j = border[0]
        self.rid[j][i] = 0
        return True


def _point_key(x: float, y: float) -> tuple[float, float]:
    return (round(x, 6), round(y, 6))


def _edge_key(
    a: tuple[float, float], b: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    return (a, b) if a <= b else (b, a)


def _pick_boundary_next(
    prev: tuple[float, float],
    curr: tuple[float, float],
    neighbors: list[tuple[float, float]],
) -> tuple[float, float] | None:
    """CCW exterior walk on orthogonal outline (interior on the left)."""
    candidates = [n for n in neighbors if n != prev]
    if not candidates:
        return None
    in_v = (curr[0] - prev[0], curr[1] - prev[1])
    if abs(in_v[0]) < 1e-9 and abs(in_v[1]) < 1e-9:
        return min(candidates, key=lambda n: (n[1], n[0]))

    def rank(n: tuple[float, float]) -> tuple[float, float]:
        out_v = (n[0] - curr[0], n[1] - curr[1])
        cross = in_v[0] * out_v[1] - in_v[1] * out_v[0]
        dot = in_v[0] * out_v[0] + in_v[1] * out_v[1]
        return (cross, -dot)

    return max(candidates, key=rank)


def _dedupe_polygon(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(pts) < 3:
        return pts
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or abs(out[-1][0] - p[0]) > 1e-6 or abs(out[-1][1] - p[1]) > 1e-6:
            out.append(p)
    if len(out) >= 2 and abs(out[0][0] - out[-1][0]) < 1e-6 and abs(out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out if len(out) >= 3 else pts
