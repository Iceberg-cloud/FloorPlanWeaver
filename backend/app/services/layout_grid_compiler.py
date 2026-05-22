"""Grid-based semantic layout compiler (0.25m cells, 100% interior coverage)."""
from __future__ import annotations
from app.schemas.layout import LayoutDraft, LayoutRoom, Point2D, SiteOutline
from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import SemanticLayoutPlan
from app.services.layout_compiler import (
    POLYGON_ROOM_TYPES, _SERVICE_TYPES,
    _build_entries_from_llm, _corner_orders, _edge_to_corners,
    _entry_room_type, _extract_llm_constraints,
    _reassign_corners_for_avoidance, _sort_fixed_entries,
    _sort_flexible_entries, _spread_zone_corners, _unique_room_label,
)
from app.services.layout_geometry import bbox_of_polygon
from app.services.layout_grid import CELL_AREA, GridMap
from app.services.layout_llm_hints import (
    sort_cells_by_world_center,
    sort_corners_by_hint,
    target_area_from_hint,
    world_center_from_normalized,
)
from app.services.layout_placement_order import (
    is_living_dining,
    split_fixed_flex_by_priority,
)
from app.services.semantic_validator import reconcile_semantic_with_program


def _target_cells_for_entry(entry, raw_targets: dict, scale: float, bbox_area: float) -> int:
    base_area = entry.target_area
    if entry.hint_width_ratio and entry.hint_height_ratio:
        base_area = target_area_from_hint(
            entry.target_area,
            entry.hint_width_ratio,
            entry.hint_height_ratio,
            bbox_area,
        )
    return max(1, int(round(GridMap.target_cells(base_area) * scale)))


def _strip_band_setup(grid, semantic, entrance_side):
    """Map rooms to strip band indices and cell bounds."""
    n = max(1, len(semantic.bands))
    direction = semantic.strip_direction or "horizontal"
    room_band = {}
    room_zone_key = {}
    for bi, band in enumerate(semantic.bands):
        for name in band.order:
            room_band[name] = bi
            room_zone_key[name] = f"band{bi}"
    bounds = {}
    for bi in range(n):
        bounds[bi] = _band_cell_bounds(grid, bi, n, direction, entrance_side)
    return room_band, bounds, room_zone_key


def _band_cell_bounds(grid, band_idx, n_bands, direction, entrance_side):
    """Compute cell bounds for a strip band."""
    if direction == "vertical":
        step = max(1, grid.cols // n_bands)
        if entrance_side == "left":
            i0 = band_idx * step
            i1 = grid.cols if band_idx == n_bands - 1 else (band_idx + 1) * step
        else:
            i1 = grid.cols - band_idx * step
            i0 = 0 if band_idx == n_bands - 1 else grid.cols - (band_idx + 1) * step
        return (i0, 0, i1, grid.rows)
    step = max(1, grid.rows // n_bands)
    if entrance_side == "bottom":
        j0 = band_idx * step
        j1 = grid.rows if band_idx == n_bands - 1 else (band_idx + 1) * step
    elif entrance_side == "top":
        j1 = grid.rows - band_idx * step
        j0 = 0 if band_idx == n_bands - 1 else grid.rows - (band_idx + 1) * step
    else:
        j0 = band_idx * step
        j1 = grid.rows if band_idx == n_bands - 1 else (band_idx + 1) * step
    return (0, j0, grid.cols, j1)


def _strip_cell_zone_key(i, j, grid, n_bands, direction, entrance_side):
    """Determine which band a cell belongs to."""
    if direction == "vertical":
        step = max(1, grid.cols // n_bands)
        bi = min(n_bands - 1, (i // step if entrance_side == "left" else (grid.cols - 1 - i) // step))
    else:
        step = max(1, grid.rows // n_bands)
        if entrance_side == "bottom":
            bi = min(n_bands - 1, j // step)
        elif entrance_side == "top":
            bi = min(n_bands - 1, (grid.rows - 1 - j) // step)
        else:
            bi = min(n_bands - 1, j // step)
    return f"band{bi}"


def _map_program_labels_to_strip(plan, room_band, zone_keys):
    """Map 次卧1/次卧2 labels to the same strip band as 次卧."""
    for item in plan.space_program:
        count = max(1, item.count)
        bi = room_band.get(item.room_type)
        if bi is None:
            continue
        zk = zone_keys.get(item.room_type, f"band{bi}")
        for idx in range(1, count + 1):
            label = _unique_room_label(item.room_type, idx, count)
            room_band[label] = bi
            zone_keys[label] = zk


def compile_semantic_layout_grid_legacy(semantic, plan, outline):
    if not outline.vertices:
        return LayoutDraft(compile_method="grid")
    poly = [(v.x, v.y) for v in outline.vertices]
    from app.services.layout_geometry import bbox_of_polygon
    min_x, min_y, max_x, max_y = bbox_of_polygon(poly)
    bbox_w, bbox_h = max_x - min_x, max_y - min_y
    if bbox_w < 0.5 or bbox_h < 0.5:
        return LayoutDraft(outline_vertices=outline.vertices, entrance_edge=outline.entrance_edge, compile_method="grid")

    semantic = reconcile_semantic_with_program(plan, semantic)
    constraints = _extract_llm_constraints(semantic, outline, min_x, min_y, max_x, max_y)
    entries = _build_entries_from_llm(plan, semantic, constraints)
    grid = GridMap.from_outline(poly)
    all_entries = list(entries.fixed) + list(entries.flexible)
    inside_total = grid.total_inside()
    raw_targets = {e.name: GridMap.target_cells(e.target_area) for e in all_entries}
    raw_sum = sum(raw_targets.values())
    scale = min(1.0, inside_total / raw_sum) if raw_sum > inside_total else 1.0

    strip_mode = semantic.layout_style == "strip" and len(semantic.bands) >= 1
    strip_room_band, strip_band_bounds, strip_zone_keys = {}, {}, {}
    if strip_mode:
        strip_room_band, strip_band_bounds, strip_zone_keys = _strip_band_setup(grid, semantic, constraints.entrance_side)
        _map_program_labels_to_strip(plan, strip_room_band, strip_zone_keys)

    back_order, front_order = _corner_orders(constraints.entrance_side)
    all_corners = list(dict.fromkeys(back_order + front_order))
    _spread_zone_corners(entries.fixed, "back", all_corners)
    _spread_zone_corners(entries.fixed, "front", all_corners)
    _spread_zone_corners(entries.fixed, "back", all_corners)
    entries.fixed = _reassign_corners_for_avoidance(entries.fixed, constraints)
    fixed_prepped = _sort_fixed_entries(entries.fixed, constraints)
    flex_prepped = _sort_flexible_entries(entries.flexible, constraints)
    tier1_fixed, kitchen_fixed, flex_sorted = split_fixed_flex_by_priority(
        fixed_prepped, flex_prepped,
    )
    placement_order = tier1_fixed + kitchen_fixed + flex_sorted

    room_id_by_name, room_targets, room_zones = {}, {}, {}
    used_corners = set()

    def _place_entry(entry, *, is_flex: bool) -> None:
        nonlocal used_corners
        rid = room_id_by_name.get(entry.name) or grid.register_room(entry.name)
        room_id_by_name[entry.name] = rid
        target = room_targets.get(rid) or _target_cells_for_entry(
            entry, raw_targets, scale, bbox_w * bbox_h,
        )
        room_targets[rid] = target
        rt = _entry_room_type(entry)
        if strip_mode:
            room_zones[rid] = strip_zone_keys.get(
                entry.name, strip_zone_keys.get(rt, "band0"),
            )
            zb = strip_band_bounds.get(
                strip_room_band.get(entry.name, strip_room_band.get(rt, 0)),
            )
        elif rt == "书房":
            room_zones[rid] = "back"
            zb = grid.zone_cell_bounds(constraints.entrance_side, "back")
        elif is_flex or is_living_dining(rt):
            room_zones[rid] = "front"
            zb = grid.zone_cell_bounds(constraints.entrance_side, "front")
        else:
            room_zones[rid] = entry.zone
            zb = None
        if is_flex or is_living_dining(rt):
            prefer_entrance = rt == "客厅"
            if strip_mode and zb:
                pool = grid.free_cells_in_bounds(
                    zb, entrance_side=constraints.entrance_side, prefer_low_y=prefer_entrance,
                )
            else:
                pool = grid.free_cells_sorted(
                    constraints.entrance_side, zone="front", prefer_low_y=prefer_entrance,
                )
            if len(pool) < target:
                extra = grid.free_cells_sorted(constraints.entrance_side, prefer_low_y=prefer_entrance)
                pool = pool + [c for c in extra if c not in pool]
            if not pool:
                pool = grid.free_cells_sorted(constraints.entrance_side, prefer_low_y=False)
            if entry.hint_center_x is not None and entry.hint_center_y is not None:
                wx, wy = world_center_from_normalized(
                    entry.hint_center_x, entry.hint_center_y, min_x, min_y, max_x, max_y,
                )
                pool = sort_cells_by_world_center(pool, grid, wx, wy)
            if pool:
                grid.bfs_claim(rid, pool[0], target)
            if grid.count_room(rid) < target:
                remaining = target - grid.count_room(rid)
                grid.claim_free_in_zone(
                    rid, "front", constraints.entrance_side, remaining, zone_bounds=zb,
                )
            if grid.count_room(rid) < 1:
                all_free = grid.free_cells_sorted(
                    constraints.entrance_side, prefer_low_y=prefer_entrance,
                )
                if all_free:
                    grid.bfs_claim(rid, all_free[0], target)
            return

        if strip_mode:
            room_zones[rid] = strip_zone_keys.get(entry.name, strip_zone_keys.get(rt, "band0"))
        elif entry.zone == "flexible":
            room_zones[rid] = "back" if rt == "书房" else "front"
        else:
            room_zones[rid] = entry.zone
        zb = strip_band_bounds.get(strip_room_band.get(entry.name, strip_room_band.get(rt, 0))) if strip_mode else None
        candidates = _edge_to_corners(entry.prefer_edge, constraints.entrance_side, entry.zone)
        if entry.corner_hint:
            candidates = [entry.corner_hint] + [c for c in candidates if c != entry.corner_hint]
        candidates = sort_corners_by_hint(candidates, entry.hint_center_x, entry.hint_center_y)
        for c in back_order + front_order:
            if c not in candidates and c not in used_corners:
                candidates.append(c)
        placed = False
        allow_notch = rt not in _SERVICE_TYPES
        for corner in candidates:
            if grid.place_rect_room(
                rid, corner, entry.zone, constraints.entrance_side, target,
                allow_notch=allow_notch, zone_bounds=zb,
            ):
                entry.corner_hint = corner
                used_corners.add(corner)
                placed = True
                break
        if not placed:
            for corner in back_order + front_order:
                if grid.place_rect_room(
                    rid, corner, entry.zone, constraints.entrance_side, target,
                    allow_notch=allow_notch, zone_bounds=zb,
                ):
                    used_corners.add(corner)
                    placed = True
                    break
        if not placed:
            grid.claim_free_in_zone(
                rid, entry.zone, constraints.entrance_side, target, zone_bounds=zb,
            )

    # Phase 1–2: 卫生间/阳台/卧室 → 厨房
    for entry in tier1_fixed + kitchen_fixed:
        _place_entry(entry, is_flex=False)

    # Phase 3: 客厅/餐厅占用剩余大区
    for entry in flex_sorted:
        _place_entry(entry, is_flex=True)

    # Fill remaining interior cells (客厅/餐厅优先扩展)
    priority = [
        room_id_by_name[e.name]
        for e in placement_order
        if e.name in room_id_by_name
    ]
    caps = {}
    for rid, t in room_targets.items():
        name = grid.room_names.get(rid, "")
        mult = 1.55 if is_living_dining(name) or name in ("客厅", "餐厅") else 1.12
        caps[rid] = max(1, int(t * mult))
    if strip_mode:
        n_bands = len(semantic.bands)
        def _strip_zone_resolver(i, j):
            return _strip_cell_zone_key(i, j, grid, n_bands, semantic.strip_direction or "horizontal", constraints.entrance_side)
        grid.fill_all_free_zoned(priority, room_zones, caps, _strip_zone_resolver)
        grid.fill_all_free_zoned(priority, room_zones, None, _strip_zone_resolver)
    else:
        grid.fill_all_free(priority, constraints.entrance_side, room_zones, caps)
        grid.fill_all_free(priority, constraints.entrance_side, room_zones)
    grid.force_fill_remaining(priority, prefer_living_last=True)

    rooms = _export_rooms(grid, placement_order, room_id_by_name, outline.vertices)
    return LayoutDraft(canvas={"width": bbox_w, "height": bbox_h}, outline_vertices=outline.vertices,
                       entrance_edge=outline.entrance_edge, rooms=rooms, doors=[], windows=[], compile_method="grid")


def _export_rooms(grid, entries, room_id_by_name, outline_vertices):
    rooms = []
    idx = 0
    for entry in entries:
        name = entry.name
        rt = _entry_room_type(entry)
        rid = room_id_by_name.get(name)
        if rid is None: continue
        idx += 1
        if grid.count_room(rid) < 1: continue
        is_polygon_type = rt in POLYGON_ROOM_TYPES
        single_rect = grid.cells_are_single_rect(rid)
        if is_polygon_type and not single_rect:
            pts = grid.cells_to_boundary_polygon(rid)
            if len(pts) < 3:
                pts = grid.cells_to_bbox_polygon(rid)
        else:
            pts = grid.cells_to_bbox_polygon(rid)
        if len(pts) < 3: continue
        area = round(grid.count_room(rid) * CELL_AREA, 1)
        shape_kind = "polygon" if is_polygon_type and not single_rect else "rect"
        if is_polygon_type and single_rect: shape_kind = "polygon"
        rooms.append(LayoutRoom(id=f"r{idx}", name=name, type=rt,
                                polygon=[Point2D(x=x, y=y) for x, y in pts],
                                area_sqm=area, adjacent_to=[], shape_kind=shape_kind))
    return rooms


def compile_semantic_layout_grid(semantic, plan, outline):
    """Method A entry: constraint + grid beam search (falls back to legacy inside)."""
    from app.services.layout_grid_search_compiler import compile_semantic_layout_grid_search

    layout, notes = compile_semantic_layout_grid_search(semantic, plan, outline)
    return layout, notes
