"""Placement order: service/bedroom → kitchen → living/dining on remaining area."""

from __future__ import annotations

from typing import Any

# 与 grid_search 一致：阳台 → 卫 → 卧 → 厨 → 书房 → 餐 → 厅
_TIER1_TYPES = frozenset({
    "阳台",
    "卫生间", "主卫", "客卫", "洗手间", "厕所",
    "主卧", "次卧", "卧室", "儿童房",
})

# Tier 2: 厨房
_TIER2_TYPES = frozenset({"厨房"})

# Tier 3: 客厅、餐厅 — 占用剩余大区（flexible）
_TIER3_TYPES = frozenset({"客厅", "餐厅", "起居室", "客餐厅"})

# 书房等：介于 tier2 与 tier3 之间
_TIER25_TYPES = frozenset({"书房", "玄关", "储物间", "衣帽间"})


def placement_tier(room_type: str) -> int:
    rt = (room_type or "").strip()
    if rt in _TIER1_TYPES:
        return 1
    if rt in _TIER2_TYPES:
        return 2
    if rt in _TIER25_TYPES:
        return 25
    if rt in _TIER3_TYPES:
        return 3
    return 4


def is_living_dining(room_type: str) -> bool:
    return (room_type or "") in _TIER3_TYPES


def sort_entries_by_placement_priority(entries: list[Any]) -> list[Any]:
    """Stable sort: tier asc, then LLM center_y (public low), center_x."""

    def key(e: Any) -> tuple:
        rt = getattr(e, "room_type", "") or getattr(e, "name", "")
        tier = placement_tier(rt)
        cy = getattr(e, "hint_center_y", None)
        cx = getattr(e, "hint_center_x", None)
        cy_k = cy if cy is not None else (0.85 if tier >= 3 else 0.35)
        cx_k = cx if cx is not None else 0.5
        return (tier, cy_k, cx_k, getattr(e, "name", ""))

    return sorted(entries, key=key)


def split_fixed_flex_by_priority(
    fixed: list[Any],
    flexible: list[Any],
) -> tuple[list[Any], list[Any], list[Any]]:
    """Returns (tier1_fixed, kitchen_fixed, flex_including_living)."""
    tier1: list[Any] = []
    kitchen: list[Any] = []
    flex: list[Any] = list(flexible)
    other: list[Any] = []

    for e in fixed:
        rt = getattr(e, "room_type", "") or ""
        if is_living_dining(rt):
            flex.append(e)
        elif rt in _TIER2_TYPES:
            kitchen.append(e)
        elif placement_tier(rt) == 1:
            tier1.append(e)
        else:
            other.append(e)

    tier1 = sort_entries_by_placement_priority(tier1)
    kitchen = sort_entries_by_placement_priority(kitchen)
    other = sort_entries_by_placement_priority(other)
    flex = sort_entries_by_placement_priority(flex)

    return (
        tier1 + other,
        kitchen,
        flex,
    )
