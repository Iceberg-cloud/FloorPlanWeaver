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

    # Grow undersized flex rooms (客厅优先) then shrink oversized
    from app.services.layout_grid_search import _trim_oversized_flex_rooms

    flex_only = [c for c in constraints if c.room_type in _FLEX_GROW_PRIORITY]
    for _ in range(6):
        _area_correction_grow(state, grid, constraints)
    for _ in range(4):
        _area_correction_shrink(state, grid, constraints)

    for c in constraints:
        if not c.must_be_rectangle:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        if not _cells_single_rect(state, grid, rid):
            cap = max(4, int(GridMap.target_cells(c.target_area_sqm) * 1.35))
            _force_rect(state, grid, rid, max_cells=cap)
            log.append(f"「{c.name}」强制回退为矩形 bbox")

    # Hard rect enforcement pass: for bathroom/bedroom/balcony, must be solid rect
    _HARD_RECT_TYPES = frozenset({
        "卫生间", "主卫", "客卫", "洗手间", "厕所",
        "主卧", "次卧", "卧室", "儿童房",
        "阳台",
    })
    for c in constraints:
        if c.room_type not in _HARD_RECT_TYPES:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        if not _cells_single_rect(state, grid, rid):
            cap = max(4, int(GridMap.target_cells(c.target_area_sqm) * 1.35))
            _force_rect(state, grid, rid, max_cells=cap)
            log.append(f"「{c.name}」二次矩形化强制")

    before = _count_unassigned(state, grid)
    if before > 0:
        _merge_fragments(state, grid, plan)
        after = _count_unassigned(state, grid)
        if after < before:
            log.append(f"最终碎片吸收：{before} → {after}")

    for _ in range(4):
        _area_correction_grow(state, grid, constraints)
    for _ in range(4):
        _area_correction_shrink(state, grid, constraints)

    healed = _heal_disconnected_rect_rooms(state, grid, constraints)
    if healed:
        log.extend(healed)
        before = _count_unassigned(state, grid)
        if before > 0:
            _merge_fragments(state, grid, plan)
            for _ in range(2):
                _area_correction_shrink(state, grid, constraints)

    for c in constraints:
        if not c.must_be_rectangle:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        if not _cells_single_rect(state, grid, rid):
            log.append(f"「{c.name}」非矩形连通块")

    # Last step: hard-rect rooms must stay solid (no merge after this)
    _HARD_RECT_TYPES = frozenset({
        "卫生间", "主卫", "客卫", "洗手间", "厕所",
        "主卧", "次卧", "卧室", "儿童房",
        "阳台",
    })
    hard_rect_rids: set[int] = set()
    for c in constraints:
        if c.room_type not in _HARD_RECT_TYPES:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        hard_rect_rids.add(rid)
        if not _cells_single_rect(state, grid, rid):
            max_cells = max(
                4,
                int(GridMap.target_cells(c.target_area_sqm) * 1.35),
            )
            if _compact_to_solid_rect(state, grid, rid, max_cells=max_cells):
                log.append(f"「{c.name}」压实为实心矩形")

    if _count_unassigned(state, grid) > 0:
        _merge_fragments(state, grid, plan, exclude_rids=hard_rect_rids)

    from app.services.layout_grid_search import _flex_cap_cells_by_rid

    _trim_oversized_flex_rooms(state, grid, flex_only)
    flex_caps = _flex_cap_cells_by_rid(flex_only, state)
    if _count_unassigned(state, grid) > 0:
        _merge_fragments(
            state, grid, plan,
            exclude_rids=hard_rect_rids,
            max_cells_by_rid=flex_caps,
        )

    from app.services.layout_grid_search import _fill_all_interior_cells

    n_fill = _fill_all_interior_cells(state, grid, flex_only, constraints)
    if n_fill:
        log.append(f"轮廓内补全：{n_fill} 格")

    healed_all = _heal_disconnected_components(state, grid, constraints)
    if healed_all:
        log.extend(healed_all)
        if _count_unassigned(state, grid) > 0:
            _merge_fragments(state, grid, plan, exclude_rids=hard_rect_rids)
            _fill_all_interior_cells(state, grid, flex_only, constraints)

    # Re-compact any hard-rect room that exceeded its area cap after fill/heal
    for c in constraints:
        if c.room_type not in _HARD_RECT_TYPES:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        max_cells = max(4, int(GridMap.target_cells(c.target_area_sqm) * 1.35))
        cur = sum(1 for j in range(grid.rows) for i in range(grid.cols)
                  if grid.inside[j][i] and state.rid[j][i] == rid)
        if cur > max_cells or not _cells_single_rect(state, grid, rid):
            _compact_to_solid_rect(state, grid, rid, max_cells=max_cells)

    # After re-compaction, heal any newly disconnected rooms
    healed2 = _heal_disconnected_components(state, grid, constraints)
    if healed2:
        log.extend(healed2)

    if not log:
        log.append("无需自动修复")
    return log


_FLEX_GROW_PRIORITY = ("客厅", "起居室", "客餐厅", "餐厅", "书房")
_LIVING_TYPES = frozenset({"客厅", "起居室", "客餐厅"})


def _grow_priority(room_type: str) -> int:
    try:
        return _FLEX_GROW_PRIORITY.index(room_type)
    except ValueError:
        return 99


def _grow_room_one_free_cell(state: SearchState, grid: GridMap, rid: int) -> bool:
    for j in range(grid.rows):
        for i in range(grid.cols):
            if state.rid[j][i] != rid:
                continue
            for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                    if grid.inside[nj][ni] and state.rid[nj][ni] == 0:
                        state.rid[nj][ni] = rid
                        return True
    return False


def _area_correction_grow(
    state: SearchState,
    grid: GridMap,
    constraints: list[RoomPlacementConstraint],
) -> None:
    """Expand undersized flexible rooms; 客厅 first (typical ~25–35% of usable area)."""
    flex_types = set(_FLEX_GROW_PRIORITY)
    targets: dict[int, tuple[float, float, str]] = {}
    for c in constraints:
        rid = state.name_to_rid.get(c.name)
        if rid is None or c.room_type not in flex_types:
            continue
        tol = c.area_tolerance + (0.05 if c.room_type in _LIVING_TYPES else 0.0)
        targets[rid] = (c.target_area_sqm, tol, c.room_type)

    sorted_rids = sorted(
        targets.keys(),
        key=lambda r: _grow_priority(targets[r][2]),
    )

    for _ in range(40):
        grew = False
        for rid in sorted_rids:
            target, tol, rt = targets[rid]
            cur = _count_rid(state, grid, rid) * CELL_AREA
            cap_hi = target * (1.0 + min(0.08, tol * 0.25) if rt in _LIVING_TYPES else 1.0 + min(0.15, tol * 0.5))
            if cur >= cap_hi * 0.98:
                continue
            if cur >= target * (1.0 - max(0.12, tol * 0.5)):
                continue
            if _grow_room_one_free_cell(state, grid, rid):
                grew = True
        if not grew:
            break


def _area_correction_shrink(
    state: SearchState,
    grid: GridMap,
    constraints: list[RoomPlacementConstraint],
) -> None:
    """Shrink oversized rooms by donating border cells to undersized neighbors.

    Key constraint: never shrink a room below its minimum viable size (4 cells).
    Never donate to a neighbor if doing so would disconnect either room.
    """
    flex_types = {"客厅", "餐厅", "起居室", "客餐厅", "书房"}
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


def _force_rect(
    state: SearchState,
    grid: GridMap,
    rid: int,
    *,
    max_cells: int | None = None,
) -> None:
    """Replace room cells with their axis-aligned bounding box.

    Claims unassigned cells and re-assigns flexible-room cells (living/dining)
    inside the bbox to ensure a complete rectangular shape.

    If the full bbox cannot be filled (other non-flex rooms in the way),
    tries the largest inscribed axis-aligned rectangle within the existing cells.
    After displacing flexible rooms, attempts to compensate them with
    nearby free cells to minimize area loss.
    """
    cells = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
             if grid.inside[j][i] and state.rid[j][i] == rid]
    if not cells:
        return

    flex_types = {"客厅", "餐厅", "起居室", "客餐厅"}

    # Strategy 1: Try full bbox expansion first
    is_ = [c[0] for c in cells]
    js_ = [c[1] for c in cells]
    i0, i1 = min(is_), max(is_)
    j0, j1 = min(js_), max(js_)

    # Check if full bbox is achievable
    can_fill_bbox = True
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            if not grid.inside[j][i]:
                can_fill_bbox = False
                break
            owner = state.rid[j][i]
            if owner == rid or owner == 0:
                continue
            other_name = state.room_names.get(owner, "")
            if any(ft in other_name for ft in flex_types):
                continue
            can_fill_bbox = False
            break
        if not can_fill_bbox:
            break

    bbox_cells = (i1 - i0 + 1) * (j1 - j0 + 1)
    if can_fill_bbox and (max_cells is None or bbox_cells <= max_cells):
        _fill_bbox_and_compensate(state, grid, rid, i0, i1, j0, j1, flex_types)
        return

    # Strategy 2: largest inscribed axis-aligned rectangle (may shrink vs bbox)
    if _compact_to_solid_rect(state, grid, rid, max_cells=max_cells):
        return

    # Strategy 3: Fall back to bbox only when within area cap
    if max_cells is None or bbox_cells <= max_cells:
        _fill_bbox_and_compensate(state, grid, rid, i0, i1, j0, j1, flex_types)
        if not _cells_single_rect(state, grid, rid):
            _compact_to_solid_rect(state, grid, rid, max_cells=max_cells)


_FLEX_TYPES = frozenset({"客厅", "餐厅", "起居室", "客餐厅"})


def _compact_to_solid_rect(
    state: SearchState,
    grid: GridMap,
    rid: int,
    *,
    max_cells: int | None = None,
) -> bool:
    """Shrink room to the largest fully-fillable axis-aligned rectangle."""
    if _cells_single_rect(state, grid, rid):
        return True
    cells = _room_cells(state, grid, rid)
    if not cells:
        return False
    flex_types = set(_FLEX_TYPES)
    best_rect = _find_largest_inscribed_rect(
        state, grid, rid, cells, flex_types, max_cells=max_cells,
    )
    if not best_rect:
        return False
    ri0, ri1, rj0, rj1 = best_rect
    _apply_solid_rect_region(state, grid, rid, ri0, ri1, rj0, rj1, flex_types)
    return _cells_single_rect(state, grid, rid)


def _apply_solid_rect_region(
    state: SearchState,
    grid: GridMap,
    rid: int,
    i0: int,
    i1: int,
    j0: int,
    j1: int,
    flex_types: set[str],
) -> None:
    """Assign exactly the axis-aligned cell block [i0..i1]×[j0..j1] to rid."""
    for j in range(grid.rows):
        for i in range(grid.cols):
            if state.rid[j][i] == rid and not (i0 <= i <= i1 and j0 <= j <= j1):
                state.rid[j][i] = 0

    displaced: dict[int, list[tuple[int, int]]] = {}
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            if not grid.inside[j][i]:
                continue
            owner = state.rid[j][i]
            if owner == rid:
                continue
            if owner == 0:
                state.rid[j][i] = rid
                continue
            other_name = state.room_names.get(owner, "")
            if any(ft in other_name for ft in flex_types):
                displaced.setdefault(owner, []).append((i, j))
                state.rid[j][i] = rid

    _compensate_displaced_flex(state, grid, displaced)


def _compensate_displaced_flex(
    state: SearchState,
    grid: GridMap,
    displaced: dict[int, list[tuple[int, int]]],
) -> None:
    for other_rid, lost_cells in displaced.items():
        lost_count = len(lost_cells)
        if lost_count == 0:
            continue
        remaining = [
            (i, j) for j in range(grid.rows) for i in range(grid.cols)
            if grid.inside[j][i] and state.rid[j][i] == other_rid
        ]
        if not remaining:
            continue
        compensated = 0
        visited: set[tuple[int, int]] = set()
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
                for ni, nj in ((fi + 1, fj), (fi - 1, fj), (fi, fj + 1), (fi, fj - 1)):
                    if (ni, nj) not in visited and 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                        if grid.inside[nj][ni] and state.rid[nj][ni] == 0:
                            visited.add((ni, nj))
                            queue.append((ni, nj))


def _fill_bbox_and_compensate(
    state: SearchState, grid: GridMap, rid: int,
    i0: int, i1: int, j0: int, j1: int,
    flex_types: set[str],
) -> None:
    """Fill bbox by displacing flex rooms and claiming free cells, then compensate."""
    _apply_solid_rect_region(state, grid, rid, i0, i1, j0, j1, flex_types)


def _find_largest_inscribed_rect(
    state: SearchState,
    grid: GridMap,
    rid: int,
    cells: list[tuple[int, int]],
    flex_types: set[str],
    *,
    max_cells: int | None = None,
) -> tuple[int, int, int, int] | None:
    """Find the largest axis-aligned inscribed rectangle using the existing cells.

    Uses a maximal-rectangle approach on the grid where each cell is "available"
    if it belongs to rid, is free, or belongs to a flex room.
    """
    is_ = [c[0] for c in cells]
    js_ = [c[1] for c in cells]
    i0, i1 = min(is_), max(is_)
    j0, j1 = min(js_), max(js_)

    # Build height map: for each (i, j), how many consecutive "available" cells above
    width = i1 - i0 + 1
    height = j1 - j0 + 1
    if width <= 0 or height <= 0:
        return None

    heights = [0] * width
    best_area = 0
    best_rect = None

    for j in range(j0, j1 + 1):
        for idx in range(width):
            i = i0 + idx
            if not grid.inside[j][i]:
                heights[idx] = 0
                continue
            owner = state.rid[j][i]
            if owner == rid or owner == 0:
                heights[idx] += 1
            elif any(ft in state.room_names.get(owner, "") for ft in flex_types):
                heights[idx] += 1
            else:
                heights[idx] = 0

        # Find max rectangle in this row's histogram
        rect = _max_rect_in_histogram(heights, i0, j)
        if not rect:
            continue
        area, _, ri0, ri1 = rect
        if max_cells is not None and area > max_cells:
            continue
        if area > best_area:
            best_area = area
            best_rect = (ri0, ri1, j - rect[1] + 1, j)

    return best_rect


def _max_rect_in_histogram(
    heights: list[int], i0: int, current_j: int,
) -> tuple[int, int, int, int] | None:
    """Return (area, height, start_i, end_i) for max rectangle in histogram."""
    stack: list[int] = []
    best = None
    n = len(heights)

    for idx in range(n + 1):
        h = heights[idx] if idx < n else 0
        while stack and heights[stack[-1]] > h:
            top = stack.pop()
            rect_h = heights[top]
            rect_w = idx if not stack else idx - stack[-1] - 1
            area = rect_h * rect_w
            if best is None or area > best[0]:
                start_i = i0 + (0 if not stack else stack[-1] + 1)
                end_i = i0 + idx - 1
                best = (area, rect_h, start_i, end_i)
        stack.append(idx)

    return best


def _room_cells(state: SearchState, grid: GridMap, rid: int) -> list[tuple[int, int]]:
    return [
        (i, j) for j in range(grid.rows) for i in range(grid.cols)
        if grid.inside[j][i] and state.rid[j][i] == rid
    ]


def _room_connected(cells: list[tuple[int, int]]) -> bool:
    if not cells:
        return False
    target = set(cells)
    seen = {cells[0]}
    q: deque[tuple[int, int]] = deque([cells[0]])
    while q:
        i, j = q.popleft()
        for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if (ni, nj) in target and (ni, nj) not in seen:
                seen.add((ni, nj))
                q.append((ni, nj))
    return len(seen) == len(target)


def _heal_disconnected_components(
    state: SearchState,
    grid: GridMap,
    constraints: list[RoomPlacementConstraint],
) -> list[str]:
    """Reassign non-main connected components to adjacent rooms."""
    log: list[str] = []
    for c in constraints:
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        cells = _room_cells(state, grid, rid)
        if _room_connected(cells):
            continue
        target = set(cells)
        seen: set[tuple[int, int]] = set()
        comps: list[list[tuple[int, int]]] = []
        for seed in cells:
            if seed in seen:
                continue
            comp: list[tuple[int, int]] = []
            q: deque[tuple[int, int]] = deque([seed])
            comp_seen = {seed}
            while q:
                i, j = q.popleft()
                comp.append((i, j))
                for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                    if (ni, nj) in target and (ni, nj) not in comp_seen:
                        comp_seen.add((ni, nj))
                        q.append((ni, nj))
            seen |= comp_seen
            comps.append(comp)
        if len(comps) <= 1:
            continue
        comps.sort(key=len, reverse=True)
        for orphan in comps[1:]:
            for i, j in orphan:
                neighbors = _neighbor_rids(state, grid, i, j, exclude=rid)
                state.rid[j][i] = neighbors[0] if neighbors else 0
        log.append(f"「{c.name}」已合并断开区域")
    return log


def _heal_disconnected_rect_rooms(
    state: SearchState,
    grid: GridMap,
    constraints: list[RoomPlacementConstraint],
) -> list[str]:
    """Reassign tiny disconnected fragments to adjacent rooms."""
    log: list[str] = []
    for c in constraints:
        if not c.must_be_rectangle:
            continue
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            continue
        cells = _room_cells(state, grid, rid)
        if _room_connected(cells):
            continue
        target = set(cells)
        seen: set[tuple[int, int]] = set()
        comps: list[list[tuple[int, int]]] = []
        for seed in cells:
            if seed in seen:
                continue
            comp: list[tuple[int, int]] = []
            q: deque[tuple[int, int]] = deque([seed])
            comp_seen = {seed}
            while q:
                i, j = q.popleft()
                comp.append((i, j))
                for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                    if (ni, nj) in target and (ni, nj) not in comp_seen:
                        comp_seen.add((ni, nj))
                        q.append((ni, nj))
            seen |= comp_seen
            comps.append(comp)
        if len(comps) <= 1:
            continue
        comps.sort(key=len, reverse=True)
        for orphan in comps[1:]:
            for i, j in orphan:
                neighbors = _neighbor_rids(state, grid, i, j, exclude=rid)
                if neighbors:
                    state.rid[j][i] = neighbors[0]
                else:
                    state.rid[j][i] = 0
        log.append(f"「{c.name}」已合并断开碎片")
    return log


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
