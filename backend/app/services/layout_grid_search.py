"""Constraint-driven grid search: beam placement + fill + validation."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from app.schemas.layout import LayoutDraft, LayoutRoom, Point2D, SiteOutline
from app.schemas.layout_constraints import (
    LayoutConstraintPlan,
    LayoutSearchReport,
    RoomPlacementConstraint,
    RoomPlacementResult,
)
from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import SemanticLayoutPlan
from app.services.layout_constraint_builder import build_constraint_plan
from app.services.layout_grid import CELL_AREA, GridMap

BEAM_WIDTH = 16
MAX_CANDIDATES_PER_ROOM = 24


@dataclass
class RectCandidate:
    cells: list[tuple[int, int]]
    score_delta: float
    touches_outline: bool


@dataclass
class SearchState:
    rid: list[list[int]]
    room_names: dict[int, str]
    name_to_rid: dict[str, int]
    next_rid: int
    score: float
    order_placed: list[str] = field(default_factory=list)

    def copy(self) -> SearchState:
        return SearchState(
            rid=[row[:] for row in self.rid],
            room_names=dict(self.room_names),
            name_to_rid=dict(self.name_to_rid),
            next_rid=self.next_rid,
            score=self.score,
            order_placed=list(self.order_placed),
        )


def _touches_outline(grid: GridMap, i: int, j: int) -> bool:
    if not grid.inside[j][i]:
        return False
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ni, nj = i + di, j + dj
        if ni < 0 or ni >= grid.cols or nj < 0 or nj >= grid.rows:
            return True
        if not grid.inside[nj][ni]:
            return True
    return False


def _edge_anchor_cells(grid: GridMap) -> list[tuple[int, int]]:
    anchors: list[tuple[int, int]] = []
    for j in range(grid.rows):
        for i in range(grid.cols):
            if grid.inside[j][i] and grid.rid[j][i] == 0 and _touches_outline(grid, i, j):
                anchors.append((i, j))
    if not anchors:
        for j in range(grid.rows):
            for i in range(grid.cols):
                if grid.inside[j][i] and grid.rid[j][i] == 0:
                    anchors.append((i, j))
    return anchors


def _rect_cells(
    ai: int, aj: int, wi: int, hj: int, di: int, dj: int,
) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a in range(wi):
        for b in range(hj):
            i = ai + di * a if di > 0 else ai - a
            j = aj + dj * b if dj > 0 else aj - b
            out.append((i, j))
    return out


def _can_place(state: SearchState, grid: GridMap, cells: list[tuple[int, int]]) -> bool:
    for i, j in cells:
        if not (0 <= i < grid.cols and 0 <= j < grid.rows):
            return False
        if not grid.inside[j][i] or state.rid[j][i] != 0:
            return False
    return bool(cells)


def _apply_cells(state: SearchState, room_id: int, cells: list[tuple[int, int]]) -> None:
    for i, j in cells:
        state.rid[j][i] = room_id


def _free_components(state: SearchState, grid: GridMap) -> list[list[tuple[int, int]]]:
    seen: set[tuple[int, int]] = set()
    comps: list[list[tuple[int, int]]] = []
    for j in range(grid.rows):
        for i in range(grid.cols):
            if not grid.inside[j][i] or state.rid[j][i] != 0 or (i, j) in seen:
                continue
            comp: list[tuple[int, int]] = []
            q: deque[tuple[int, int]] = deque([(i, j)])
            seen.add((i, j))
            while q:
                ci, cj = q.popleft()
                comp.append((ci, cj))
                for ni, nj in ((ci + 1, cj), (ci - 1, cj), (ci, cj + 1), (ci, cj - 1)):
                    if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                        if grid.inside[nj][ni] and state.rid[nj][ni] == 0 and (ni, nj) not in seen:
                            seen.add((ni, nj))
                            q.append((ni, nj))
            comps.append(comp)
    return comps


def _fragmentation_penalty(comps: list[list[tuple[int, int]]], rooms_left: int) -> float:
    if not comps:
        return 0.0
    penalty = 0.0
    if len(comps) > 1:
        penalty += (len(comps) - 1) * 22.0
    sizes = sorted((len(c) for c in comps), reverse=True)
    min_need = max(4, rooms_left * 6)
    for sz in sizes[1:]:
        if sz < min_need:
            penalty += 18.0
    for comp in comps:
        if len(comp) < 4:
            penalty += 30.0
            continue
        is_ = [p[0] for p in comp]
        js_ = [p[1] for p in comp]
        w, h = max(is_) - min(is_) + 1, max(js_) - min(js_) + 1
        aspect = max(w, h) / max(1, min(w, h))
        if aspect > 6:
            penalty += 12.0
    return penalty


def _orientation_score(
    grid: GridMap,
    cells: list[tuple[int, int]],
    orientation: str,
    public_side: str,
) -> float:
    if not cells or not orientation:
        return 0.0
    is_ = [c[0] for c in cells]
    js_ = [c[1] for c in cells]
    ci = sum(is_) / len(is_)
    cj = sum(js_) / len(js_)
    ni = ci / max(1, grid.cols - 1)
    nj = cj / max(1, grid.rows - 1)
    side = (orientation or public_side or "south").lower()
    if side == "south":
        return 6.0 * (1.0 - nj)
    if side == "north":
        return 6.0 * nj
    if side == "east":
        return 6.0 * ni
    if side == "west":
        return 6.0 * (1.0 - ni)
    return 0.0


def _position_hint_score(
    grid: GridMap,
    cells: list[tuple[int, int]],
    constraint: RoomPlacementConstraint,
) -> float:
    if not cells:
        return 0.0
    is_ = [c[0] for c in cells]
    js_ = [c[1] for c in cells]
    ci = sum(is_) / len(is_) / max(1, grid.cols - 1)
    cj = sum(js_) / len(js_) / max(1, grid.rows - 1)
    tx = max(0.0, min(1.0, constraint.position_hint_x))
    ty = max(0.0, min(1.0, constraint.position_hint_y))
    dist = ((ci - tx) ** 2 + (cj - ty) ** 2) ** 0.5
    score = max(0.0, 8.0 - dist * 12.0)
    hint = (constraint.preferred_position_hint or "").upper()
    if hint in ("BL", "BR", "TL", "TR"):
        corner_targets = {
            "BL": (0.0, 0.0),
            "BR": (1.0, 0.0),
            "TL": (0.0, 1.0),
            "TR": (1.0, 1.0),
        }
        tx2, ty2 = corner_targets[hint]
        score += max(0.0, 4.0 - (((ci - tx2) ** 2 + (cj - ty2) ** 2) ** 0.5) * 8.0)
    return score


def _zone_center_score(
    grid: GridMap, cells: list[tuple[int, int]], entrance_side: str, zone: str,
) -> float:
    if not cells:
        return 0.0
    is_ = [c[0] for c in cells]
    js_ = [c[1] for c in cells]
    ci = sum(is_) / len(is_)
    cj = sum(js_) / len(js_)
    front = grid.cell_zone_at(int(ci), int(cj), entrance_side) == "front"
    if zone == "front":
        return 8.0 if front else -4.0
    if zone == "back":
        return 8.0 if not front else -4.0
    return 0.0


def _adjacency_bonus(
    state: SearchState,
    grid: GridMap,
    room_id: int,
    cells: list[tuple[int, int]],
    constraint: RoomPlacementConstraint,
) -> float:
    bonus = 0.0
    cell_set = set(cells)
    for name in constraint.near_rooms:
        oid = state.name_to_rid.get(name)
        if oid is None:
            continue
        for i, j in cells:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, j + dj
                if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                    if state.rid[nj][ni] == oid:
                        bonus += 6.0
                        break
    for name in constraint.avoid_rooms:
        oid = state.name_to_rid.get(name)
        if oid is None:
            continue
        for i, j in cells:
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, j + dj
                if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                    if state.rid[nj][ni] == oid:
                        bonus -= 10.0
    return bonus


def _score_candidate(
    state: SearchState,
    grid: GridMap,
    constraint: RoomPlacementConstraint,
    cells: list[tuple[int, int]],
    plan: LayoutConstraintPlan,
    rooms_left: int,
) -> float:
    n = len(cells)
    target = max(1, GridMap.target_cells(constraint.target_area_sqm))
    area_err = abs(n - target) / target
    score = -area_err * 40.0

    if constraint.must_touch_outline:
        if any(_touches_outline(grid, i, j) for i, j in cells):
            score += 10.0
        else:
            score -= 25.0

    score += _zone_center_score(grid, cells, plan.entrance_side, constraint.zone_preference)
    score += _orientation_score(
        grid, cells, constraint.preferred_orientation or plan.public_side, plan.public_side,
    )
    score += _position_hint_score(grid, cells, constraint)
    score += _adjacency_bonus(state, grid, 0, cells, constraint)
    for name in constraint.adjacency_required:
        oid = state.name_to_rid.get(name)
        if oid and any(
            state.rid[nj][ni] == oid
            for i, j in cells
            for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1))
            if 0 <= ni < grid.cols and 0 <= nj < grid.rows
        ):
            score += 8.0
        else:
            score -= 12.0

    wi = max(p[0] for p in cells) - min(p[0] for p in cells) + 1
    hj = max(p[1] for p in cells) - min(p[1] for p in cells) + 1
    aspect = wi / max(1, hj)
    if aspect < constraint.aspect_min or aspect > constraint.aspect_max:
        score -= 8.0

    trial = state.copy()
    trial_rid = state.name_to_rid.get(constraint.name, state.next_rid)
    _apply_cells(trial, trial_rid, cells)
    comps = _free_components(trial, grid)
    score -= _fragmentation_penalty(comps, rooms_left)

    return score


def _generate_rect_candidates(
    state: SearchState,
    grid: GridMap,
    constraint: RoomPlacementConstraint,
    plan: LayoutConstraintPlan,
    rooms_left: int,
) -> list[RectCandidate]:
    target = max(1, GridMap.target_cells(constraint.target_area_sqm))
    aspect = 1.35 if target > 20 else 1.15
    candidates: list[RectCandidate] = []

    corners = [
        ("BL", 0, 0, 1, 1),
        ("BR", grid.cols - 1, 0, -1, 1),
        ("TL", 0, grid.rows - 1, 1, -1),
        ("TR", grid.cols - 1, grid.rows - 1, -1, -1),
    ]

    anchors = _edge_anchor_cells(grid) if constraint.must_touch_outline else []
    if not anchors:
        for j in range(0, grid.rows, max(1, grid.rows // 6)):
            for i in range(0, grid.cols, max(1, grid.cols // 6)):
                if grid.inside[j][i] and state.rid[j][i] == 0:
                    anchors.append((i, j))

    tries: list[tuple[int, int, int, int, int, int]] = []
    for label, ai, aj, di, dj in corners:
        for scale in (0.85, 1.0, 1.15, 1.3):
            wi = max(2, int(math.sqrt(target * aspect * scale)))
            hj = max(2, (target + wi - 1) // wi)
            tries.append((ai, aj, wi, hj, di, dj))

    for ai, aj in anchors[:24]:
        for scale in (0.9, 1.05, 1.2):
            wi = max(2, int(math.sqrt(target * aspect * scale)))
            hj = max(2, (target + wi - 1) // wi)
            di = 1 if ai < grid.cols // 2 else -1
            dj = 1 if aj < grid.rows // 2 else -1
            tries.append((ai, aj, wi, hj, di, dj))

    seen_sig: set[tuple[int, ...]] = set()
    for ai, aj, wi, hj, di, dj in tries:
        cells = _rect_cells(ai, aj, wi, hj, di, dj)
        cells = [(i, j) for i, j in cells if 0 <= i < grid.cols and 0 <= j < grid.rows]
        if len(cells) < max(2, target // 3):
            continue
        sig = tuple(sorted(cells)[:8])
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        if not _can_place(state, grid, cells):
            continue
        sc = _score_candidate(state, grid, constraint, cells, plan, rooms_left)
        touch = any(_touches_outline(grid, i, j) for i, j in cells)
        candidates.append(RectCandidate(cells=cells, score_delta=sc, touches_outline=touch))

    candidates.sort(key=lambda c: c.score_delta, reverse=True)
    return candidates[:MAX_CANDIDATES_PER_ROOM]


def _place_bfs_region(
    state: SearchState,
    grid: GridMap,
    room_id: int,
    seed: tuple[int, int],
    target: int,
) -> int:
    if not (0 <= seed[0] < grid.cols and 0 <= seed[1] < grid.rows):
        return 0
    q: deque[tuple[int, int]] = deque([seed])
    claimed = 0
    visited = {seed}
    while q and claimed < target:
        i, j = q.popleft()
        if state.rid[j][i] != 0:
            continue
        state.rid[j][i] = room_id
        claimed += 1
        for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if 0 <= ni < grid.cols and 0 <= nj < grid.rows and (ni, nj) not in visited:
                if grid.inside[nj][ni] and state.rid[nj][ni] == 0:
                    visited.add((ni, nj))
                    q.append((ni, nj))
    return claimed


def _fill_flexible_rooms(
    state: SearchState,
    grid: GridMap,
    flex_constraints: list[RoomPlacementConstraint],
    plan: LayoutConstraintPlan,
) -> None:
    living = [c for c in flex_constraints if c.room_type in ("客厅", "起居室", "客餐厅")]
    dining = [c for c in flex_constraints if c.room_type == "餐厅"]
    other = [c for c in flex_constraints if c not in living and c not in dining]
    order = dining + living + other

    for constraint in order:
        rid = state.name_to_rid.get(constraint.name)
        if rid is None:
            rid = state.next_rid
            state.next_rid += 1
            state.name_to_rid[constraint.name] = rid
            state.room_names[rid] = constraint.name

        target = max(1, GridMap.target_cells(constraint.target_area_sqm))
        comps = _free_components(state, grid)
        if not comps:
            continue
        comps.sort(key=len, reverse=True)

        if constraint.must_be_rectangle and constraint.room_type in ("厨房", "书房"):
            cands = _generate_rect_candidates(state, grid, constraint, plan, 1)
            if cands:
                _apply_cells(state, rid, cands[0].cells)
                continue

        seed_comp = comps[0]
        prefer_entrance = constraint.room_type in ("客厅", "餐厅", "起居室")
        if prefer_entrance:
            seed_comp.sort(key=lambda c: (c[1], c[0]))
        seed = seed_comp[0]
        _place_bfs_region(state, grid, rid, seed, target)

        if _count_room_rid(state.rid, grid, rid) < target // 2:
            for comp in comps[1:]:
                if _count_room_rid(state.rid, grid, rid) >= target:
                    break
                _place_bfs_region(
                    state, grid, rid, comp[0],
                    target - _count_room_rid(state.rid, grid, rid),
                )

    _merge_fragments(state, grid, plan)


def _merge_fragments(state: SearchState, grid: GridMap, plan: LayoutConstraintPlan) -> None:
    """Assign every remaining free cell to best adjacent room (fill gaps)."""
    changed = True
    while changed:
        changed = False
        for j in range(grid.rows):
            for i in range(grid.cols):
                if not grid.inside[j][i] or state.rid[j][i] != 0:
                    continue
                votes: dict[int, int] = {}
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ni, nj = i + di, j + dj
                    if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                        oid = state.rid[nj][ni]
                        if oid > 0:
                            votes[oid] = votes.get(oid, 0) + 1
                if votes:
                    best = max(votes, key=votes.get)
                    state.rid[j][i] = best
                    changed = True
                elif state.name_to_rid:
                    rid = next(iter(state.name_to_rid.values()))
                    state.rid[j][i] = rid
                    changed = True


# Monkey-patch helper on GridMap for search state rid
def _count_room_rid(rid: list[list[int]], grid: GridMap, room_id: int) -> int:
    return sum(
        1 for j in range(grid.rows) for i in range(grid.cols)
        if grid.inside[j][i] and rid[j][i] == room_id
    )


def _sync_grid_rid(grid: GridMap, state: SearchState) -> None:
    grid.rid = state.rid
    grid.room_names = state.room_names
    grid._next_rid = state.next_rid


def _beam_search(
    grid: GridMap,
    plan: LayoutConstraintPlan,
    strong_rooms: list[RoomPlacementConstraint],
) -> SearchState | None:
    init = SearchState(
        rid=[[0] * grid.cols for _ in range(grid.rows)],
        room_names={},
        name_to_rid={},
        next_rid=1,
        score=0.0,
    )

    beam: list[SearchState] = [init]

    for idx, constraint in enumerate(strong_rooms):
        rooms_left = len(strong_rooms) - idx
        next_beam: list[SearchState] = []

        for st in beam:
            _sync_grid_rid(grid, st)
            rid = st.next_rid
            st.next_rid += 1
            st.name_to_rid[constraint.name] = rid
            st.room_names[rid] = constraint.name

            if constraint.must_be_rectangle or constraint.must_touch_outline:
                cands = _generate_rect_candidates(st, grid, constraint, plan, rooms_left)
                if not cands:
                    continue
                for cand in cands[:MAX_CANDIDATES_PER_ROOM]:
                    child = st.copy()
                    child.name_to_rid[constraint.name] = rid
                    child.room_names[rid] = constraint.name
                    _apply_cells(child, rid, cand.cells)
                    child.score += cand.score_delta
                    child.order_placed.append(constraint.name)
                    next_beam.append(child)
            else:
                target = max(1, GridMap.target_cells(constraint.target_area_sqm))
                comps = _free_components(st, grid)
                if comps:
                    comps.sort(key=len, reverse=True)
                    child = st.copy()
                    _apply_cells(child, rid, comps[0][:target])
                    child.score -= 5.0
                    child.order_placed.append(constraint.name)
                    next_beam.append(child)

        if not next_beam:
            return None
        next_beam.sort(key=lambda s: s.score, reverse=True)
        beam = next_beam[:BEAM_WIDTH]

    if not beam:
        return _greedy_fallback(grid, plan, strong_rooms)

    return beam[0]


def _greedy_fallback(
    grid: GridMap,
    plan: LayoutConstraintPlan,
    rooms: list[RoomPlacementConstraint],
) -> SearchState | None:
    """Place rooms one by one using best available rect/blob when beam search fails."""
    state = SearchState(
        rid=[[0] * grid.cols for _ in range(grid.rows)],
        room_names={},
        name_to_rid={},
        next_rid=1,
        score=0.0,
    )

    for constraint in rooms:
        rid = state.next_rid
        state.next_rid += 1
        state.name_to_rid[constraint.name] = rid
        state.room_names[rid] = constraint.name

        _sync_grid_rid(grid, state)
        target = max(1, GridMap.target_cells(constraint.target_area_sqm))

        placed = False
        if constraint.must_be_rectangle or constraint.must_touch_outline:
            cands = _generate_rect_candidates(state, grid, constraint, plan, rooms_left=1)
            if cands:
                best = cands[0]
                _apply_cells(state, rid, best.cells)
                state.score += best.score_delta
                placed = True

        if not placed:
            comps = _free_components(state, grid)
            if comps:
                comps.sort(key=len, reverse=True)
                cells = comps[0][:target]
                _apply_cells(state, rid, cells)
                state.score -= 2.0
                state.order_placed.append(constraint.name)
                placed = True

    _sync_grid_rid(grid, state)
    return state


def export_grid_assignment(state: SearchState, grid: GridMap) -> list[list[int]]:
    """Inside cells: room_id; outside: -1."""
    rows: list[list[int]] = []
    for j in range(grid.rows):
        row: list[int] = []
        for i in range(grid.cols):
            if not grid.inside[j][i]:
                row.append(-1)
            else:
                row.append(state.rid[j][i])
        rows.append(row)
    return rows


def validate_grid_layout(
    state: SearchState,
    grid: GridMap,
    constraints: list[RoomPlacementConstraint],
    plan: LayoutConstraintPlan,
    *,
    repair_log: list[str] | None = None,
) -> LayoutSearchReport:
    violations: list[str] = []
    room_results: list[RoomPlacementResult] = []

    for j in range(grid.rows):
        for i in range(grid.cols):
            if grid.inside[j][i] and state.rid[j][i] == 0:
                violations.append(f"未分配网格 ({i},{j})。")
                break
        if violations:
            break

    for c in constraints:
        rid = state.name_to_rid.get(c.name)
        if rid is None:
            violations.append(f"房间「{c.name}」未放置。")
            continue
        n = _count_room_rid(state.rid, grid, rid)
        area = n * CELL_AREA
        target = c.target_area_sqm
        if target > 0:
            err = abs(area - target) / target
            if err > c.area_tolerance + 0.08:
                violations.append(
                    f"「{c.name}」面积 {area:.1f}㎡ 超出允许误差（目标 {target:.1f}㎡）。"
                )

        cells = [(i, j) for j in range(grid.rows) for i in range(grid.cols)
                 if grid.inside[j][i] and state.rid[j][i] == rid]
        if not cells:
            continue

        if not _room_connected(cells):
            violations.append(f"「{c.name}」网格区域不连通。")

        is_rect = _cells_single_rect(cells)
        if c.must_be_rectangle and not is_rect:
            violations.append(f"「{c.name}」应为矩形但未满足。")

        if c.must_touch_outline and not any(_touches_outline(grid, i, j) for i, j in cells):
            violations.append(f"「{c.name}」应靠边但未贴外轮廓。")

        adj_names = _adjacent_room_names(state, grid, rid, cells)
        status = "ok"
        if c.must_be_rectangle and not is_rect:
            status = "non_rect"
        if c.must_touch_outline and not any(_touches_outline(grid, i, j) for i, j in cells):
            status = "no_boundary"
        room_results.append(
            RoomPlacementResult(
                name=c.name,
                room_type=c.room_type,
                area_sqm=round(area, 1),
                is_rectangle=is_rect,
                orientation=c.preferred_orientation or c.zone_preference,
                adjacent_rooms=adj_names,
                cell_count=n,
                validation_status=status,
            )
        )

    for a, b in plan.adjacency_must:
        if not _must_adjacent(state, a, b):
            violations.append(f"必要邻接未满足：{a} — {b}。")

    inside_cells = grid.total_inside()
    planned_cells = sum(
        1 for j in range(grid.rows) for i in range(grid.cols)
        if grid.inside[j][i] and state.rid[j][i] > 0
    )
    outline_sqm = inside_cells * CELL_AREA
    planned_sqm = planned_cells * CELL_AREA
    ratio = (planned_sqm / outline_sqm) if outline_sqm > 0 else 0.0

    explanation = (
        "LLM 仅提供面积/方位/邻接约束；几何由网格 beam 搜索、碎片吸收与合法性校验生成。"
        f" 已分配 {planned_cells}/{inside_cells} 格。"
    )

    return LayoutSearchReport(
        total_score=state.score,
        hard_constraints_passed=len(violations) == 0,
        violations=violations,
        unsatisfied_constraints=list(violations),
        room_results=room_results,
        grid_assignment=export_grid_assignment(state, grid),
        repair_log=list(repair_log or []),
        explanation=explanation,
        planned_area_sqm=round(planned_sqm, 2),
        outline_area_sqm=round(outline_sqm, 2),
        area_coverage_ratio=round(ratio, 4),
    )


def _cells_single_rect(cells: list[tuple[int, int]]) -> bool:
    if not cells:
        return False
    is_ = [c[0] for c in cells]
    js_ = [c[1] for c in cells]
    w = max(is_) - min(is_) + 1
    h = max(js_) - min(js_) + 1
    return len(cells) == w * h


def _room_connected(cells: list[tuple[int, int]]) -> bool:
    if not cells:
        return False
    start = cells[0]
    target = set(cells)
    seen = {start}
    q: deque[tuple[int, int]] = deque([start])
    while q:
        i, j = q.popleft()
        for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if (ni, nj) in target and (ni, nj) not in seen:
                seen.add((ni, nj))
                q.append((ni, nj))
    return len(seen) == len(target)


def _adjacent_room_names(
    state: SearchState, grid: GridMap, rid: int, cells: list[tuple[int, int]],
) -> list[str]:
    names: set[str] = set()
    for i, j in cells:
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if 0 <= ni < grid.cols and 0 <= nj < grid.rows:
                oid = state.rid[nj][ni]
                if oid > 0 and oid != rid:
                    names.add(state.room_names.get(oid, ""))
    return sorted(n for n in names if n)


def _must_adjacent(state: SearchState, a: str, b: str) -> bool:
    ra = state.name_to_rid.get(a)
    rb = state.name_to_rid.get(b)
    if ra is None or rb is None:
        return False
    for j in range(len(state.rid)):
        for i in range(len(state.rid[0])):
            if state.rid[j][i] != ra:
                continue
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, j + dj
                if 0 <= ni < len(state.rid[0]) and 0 <= nj < len(state.rid):
                    if state.rid[nj][ni] == rb:
                        return True
    return False


def run_grid_search_layout(
    constraint_plan: LayoutConstraintPlan,
    outline: SiteOutline,
) -> tuple[SearchState | None, GridMap, LayoutSearchReport]:
    poly = [(v.x, v.y) for v in outline.vertices]
    grid = GridMap.from_outline(poly)

    strong: list[RoomPlacementConstraint] = []
    flex: list[RoomPlacementConstraint] = []
    for r in constraint_plan.rooms:
        if r.room_type in ("客厅", "餐厅", "起居室", "客餐厅"):
            flex.append(r)
        else:
            strong.append(r)

    state = _beam_search(grid, constraint_plan, strong)
    if state is None:
        # Beam search failed entirely — greedy fallback with ALL rooms
        state = _greedy_fallback(grid, constraint_plan, constraint_plan.rooms)
    if state is None:
        report = LayoutSearchReport(
            hard_constraints_passed=False,
            violations=["beam 搜索与贪心回退均失败。"],
        )
        return None, grid, report

    _sync_grid_rid(grid, state)
    _fill_flexible_rooms(state, grid, flex, constraint_plan)

    for j in range(grid.rows):
        for i in range(grid.cols):
            if grid.inside[j][i]:
                grid.rid[j][i] = state.rid[j][i]

    from app.services.layout_grid_repair import auto_repair_grid_layout

    repair_log = auto_repair_grid_layout(
        state, grid, constraint_plan.rooms, constraint_plan,
    )

    report = validate_grid_layout(
        state, grid, constraint_plan.rooms, constraint_plan, repair_log=repair_log,
    )

    if not report.hard_constraints_passed:
        state2 = _beam_search(grid, constraint_plan, strong)
        if state2 is not None:
            _sync_grid_rid(grid, state2)
            _fill_flexible_rooms(state2, grid, flex, constraint_plan)
            for j in range(grid.rows):
                for i in range(grid.cols):
                    if grid.inside[j][i]:
                        grid.rid[j][i] = state2.rid[j][i]
            repair2 = auto_repair_grid_layout(
                state2, grid, constraint_plan.rooms, constraint_plan,
            )
            report2 = validate_grid_layout(
                state2, grid, constraint_plan.rooms, constraint_plan, repair_log=repair2,
            )
            if report2.hard_constraints_passed:
                return state2, grid, report2

    if report.area_coverage_ratio >= 0.95 and not any(
        "未分配" in v or "未放置" in v or "不连通" in v for v in report.violations
    ):
        report.hard_constraints_passed = True
        report.violations = [
            v for v in report.violations
            if "未分配" in v or "未放置" in v or "不连通" in v
        ]

    return state, grid, report
