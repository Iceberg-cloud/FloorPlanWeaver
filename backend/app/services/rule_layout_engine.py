"""Rule-based layout engine with weighted room placement."""

from __future__ import annotations

DEFAULT_AREAS: dict[str, float] = {
    "客厅": 15.0,
    "餐厅": 10.0,
    "主卧": 12.0,
    "次卧": 10.0,
    "厨房": 6.0,
    "卫生间": 4.0,
    "阳台": 4.0,
    "书房": 8.0,
    "玄关": 3.0,
    "走廊": 4.0,
    "起居室": 12.0,
    "客餐厅": 16.0,
    "主卫": 4.0,
    "客卫": 3.0,
    "洗手间": 3.0,
    "儿童房": 9.0,
    "卧室": 10.0,
}


def build_weighted_rule_layout(plan, outline):
    """Placeholder: returns empty layout for legacy compatibility."""
    from app.schemas.layout import LayoutDraft
    return LayoutDraft()
