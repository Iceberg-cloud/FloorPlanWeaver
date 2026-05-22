"""Auto-repair grid assignments before final validation (Method A post-process)."""

from __future__ import annotations

from collections import deque

from app.schemas.layout_constraints import LayoutConstraintPlan, RoomPlacementConstraint
from app.services.layout_grid import CELL_AREA, GridMap
from app.services.layout_grid_search import SearchState, _merge_fragments


def auto_repair_grid_layout(
    state: SearchState,
    grid: GridMap,
    constraints: list[RoomPlacementConstraint],
    plan: LayoutConstraintPlan,
) -> list[str]:
    """Multi-pass auto-repair: fragment absorption → area correction → rect check."""
    log: list[str] = []

    for pass_num in range(3):
        before = _count_unassigned(state, grid)
        if before > 0:
            _merge_fragments(state, grid, plan)
            after = _count_unassigned(state, grid)
            if after < before:
                log.append(f"吸收碎片（第{pass_num+1}轮）：{before} → {after} 格")
        if _count_unassigned(state, grid) == 0:
            break

    # Bidirectional area correction: shrink oversized rooms carefully
    for _ in range(4):
        _area_correction_shrink(state, grid, constraints)

    for c in constraints:
        if not c.must_be_rectangle:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        if not _cells_single_rect(state, grid, rid):
            _force_rect(state, grid, rid)
            log.append(f"「{c.name}」强制回退为矩形 bbox")

    before = _count_unassigned(state, grid)
    if before > 0:
        _merge_fragments(state, grid, plan)
        after = _count_unassigned(state, grid)
        if after < before:
            log.append(f"最终碎片吸收：{before} → {after}")

    # Final area correction pass after rect enforcement
    for _ in range(4):
        _area_correction_shrink(state, grid, constraints)

    for c in constraints:
        if not c.must_be_rectangle:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        if not _cells_single_rect(state, grid, rid):
            log.append(f"「{c.name}」非矩形连通块")

    if not log:
        log.append("无需自动修复")
    return log


def _area_correction_shrink(
    state: SearchState,
    grid: GridMap,
    constraints: list[RoomPlacementConstraint],
) -> None:
    """Shrink oversized rooms by donating border cells to undersized neighbors.

    Key constraint: never shrink a room below its minimum viable size (4 cells).
    Never donate to a neighbor if doing so would disconnect either room.
    """
    flex_types = {"客厅", "餐厅", "起居室", "客餐厅", "书房", "厨房"}
    target_map: dict[int, float] = {}
    flex_rids: set[int] = set()
    rect_rids: set[int] = set()
    min_cells_map: dict[int, int] = {}

    for c in constraints:
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        target_map[rid] = c.target_area_sqm
        min_cells = max(4, int(c.target_area_sqm / CELL_AREA * 0.5))
        min_cells_map[rid] = min_cells
        if c.allow_non_rect and c.room_type in flex_types:
            flex_rids.add(rid)
        if c.must_be_rectangle:
            rect_rids.add(rid)

    moved_any = False
    for _ in range(30):
        moved = False
        for rid in list(rect_rids) + list(target_map.keys()):
            if rid not in target_map:
                continue
            target = target_map[rid]
            current = _count_rid(state, grid, rid)
            actual = current * CELL_AREA
            if actual <= target * 1.1:
                continue
            min_cells = min_cells_map.get(rid, 4)
            if current <= min_cells:
                continue

            excess = max(1, int((actual - target) / CELL_AREA))
            border = _border_cells(state, grid, rid)

            for i, j in border[:excess]:
                if _count_rid(state, grid, rid) <= min_cells:
                    break
                neighbors = _neighbor_rids(state, grid, i, j, exclude=rid)
                if not neighbors:
                    continue

                # Prefer donating to undersized flex rooms first
                def _need_score(nrid: int) -> float:
                    if nrid not in target_map:
                        return 0
                    n_actual = _count_rid(state, grid, nrid) * CELL_AREA
                    n_target = target_map[nrid]
                    return max(0, n_target - n_actual)

                sorted_n = sorted(neighbors, key=_need_score, reverse=True)
                target_rid = None
                if rid in rect_rids:
                    flex_n = [n for n in sorted_n if n in flex_rids]
                    if flex_n:
                        target_rid = flex_n[0]

                if target_rid is None:
                    target_rid = sorted_n[0]

                # Only donate if neighbor is actually undersized
                n_actual = _count_rid(state, grid, target_rid) * CELL_AREA
                n_target = target_map.get(target_rid, 0)
                if n_actual >= n_target * 1.1:
                    continue

                state.rid[j][i] = target_rid
                moved = True
                if _count_rid(state, grid, rid) * CELL_AREA <= target * 1.1:
                    break

        if not moved:
            break
        moved_any = True


def _border_cells(state: SearchState, grid: GridMap, rid: int) -> list[tuple[int, int]]:
    border = []
    for j in range(grid.rows):
        for i in range(grid.cols):
            if state.rid[j][i] != rid:
                continue
            for ni, nj in ((i+1,j),(i-1,j),(i,j+1),(i,j-1)):
                if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                    if state.rid[nj][ni] != rid:
                        border.append((i, j))
                        break
    return border


def _neighbor_rids(state: SearchState, grid: GridMap, i: int, j: int, exclude: int) -> list[int]:
    rids = []
    for ni, nj in ((i+1,j),(i-1,j),(i,j+1),(i,j-1)):
        if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
            rid = state.rid[nj][ni]
            if rid > 0 and rid != exclude:
                rids.append(rid)
    return list(dict.fromkeys(rids))


def _count_unassigned(state: SearchState, grid: GridMap) -> int:
    return sum(
        1 for j in range(grid.rows) for i in range(grid.cols)
        if grid.inside[j][i] and state.rid[j][i] == 0
    )


def _count_rid(state: SearchState, grid: GridMap, rid: int) -> int:
    return sum(
        1 for j in range(grid.rows) for i in range(grid.cols)
        if grid.inside[j][i] and state.rid[j][i] == rid
    )


def _shrink_room_cells(
    state: SearchState,
    grid: GridMap,
    rid: int,
    *,
    max_remove: int,
) -> int:
    removed = 0
    border: list[tuple[int, int]] = []
    for j in range(grid.rows):
        for i in range(grid.cols):
            if state.rid[j][i] != rid:
                continue
            for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                    if state.rid[nj][ni] != rid:
                        border.append((i, j))
                        break
    for i, j in border[:max_remove]:
        if _count_rid(state, grid, rid) <= 2:
            break
        state.rid[j][i] = 0
        removed += 1
    if removed:
        _merge_fragments(state, grid, LayoutConstraintPlan())
    return removed


def _force_rect(state: SearchState, grid: GridMap, rid: int) -> None:
    """Replace room cells with their axis-aligned bounding box.

    Claims unassigned cells and re-assigns flexible-room cells (living/dining)
    inside the bbox to ensure a complete rectangular shape.

    After displacing flexible rooms, attempts to compensate them with
    nearby free cells to minimize area loss.
    """
    cells = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
             if grid.inside[j][i] and state.rid[j][i] == rid]
    if not cells:
        return
    is_ = [c[0] for c in cells]
    js_ = [c[1] for c in cells]
    i0, i1 = min(is_), max(is_)
    j0, j1 = min(js_), max(js_)

    # Find flexible rooms inside the bbox that can be displaced
    flex_types = {"客厅", "餐厅", "起居室", "客餐厅"}
    displaced: dict[int, list[tuple[int, int]]] = {}
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            if not grid.inside[j][i]:
                continue
            if state.rid[j][i] == rid or state.rid[j][i] == 0:
                continue
            other_rid = state.rid[j][i]
            other_name = state.room_names.get(other_rid, "")
            if any(ft in other_name for ft in flex_types):
                displaced.setdefault(other_rid, []).append((i, j))
                state.rid[j][i] = rid

    # Fill remaining unassigned cells in bbox
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            if not grid.inside[j][i]:
                continue
            if state.rid[j][i] == rid:
                continue
            if state.rid[j][i] == 0:
                state.rid[j][i] = rid

    # Compensate displaced flexible rooms with nearby free cells
    for other_rid, lost_cells in displaced.items():
        lost_count = len(lost_cells)
        if lost_count == 0:
            continue

        # Find free cells adjacent to the displaced room's remaining cells
        remaining = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
                     if grid.inside[j][i] and state.rid[j][i] == other_rid]
        if not remaining:
            continue

        remaining_set = set(remaining)
        compensated = 0
        visited: set[tuple[int, int]] = set()

        # BFS from remaining cells to find nearby free cells
        queue: deque[tuple[int, int]] = deque()
        for ci, cj in remaining:
            for ni, nj in ((ci + 1, cj), (ci - 1, cj), (ci, cj + 1), (ci, cj - 1)):
                if (ni, nj) not in visited and 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                    if grid.inside[nj][ni] and state.rid[nj][ni] == 0:
                        visited.add((ni, nj))
                        queue.append((ni, nj))

        while queue and compensated < lost_count:
            fi, fj = queue.popleft()
            if state.rid[fj][fi] == 0:
                state.rid[fj][fi] = other_rid
                compensated += 1
                # Add neighbors of the newly claimed cell
                for ni, nj in ((fi + 1, fj), (fi - 1, fj), (fi, fj + 1), (fi, fj - 1)):
                    if (ni, nj) not in visited and 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                        if grid.inside[nj][ni] and state.rid[nj][ni] == 0:
                            visited.add((ni, nj))
                            queue.append((ni, nj))


def _cells_single_rect(state: SearchState, grid: GridMap, rid: int) -> bool:
    cells = [
        (i, j) for j in range(grid.rows) for i in range(grid.cols)
        if grid.inside[j][i] and state.rid[j][i] == rid
    ]
    if not cells:
        return False
    is_ = [c[0] for c in cells]
    js_ = [c[1] for c in cells]
    w = max(is_) - min(is_) + 1
    h = max(js_) - min(js_) + 1
    return len(cells) == w * h
