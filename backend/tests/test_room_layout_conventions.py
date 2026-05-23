import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.room_layout_conventions import (
    build_default_bands,
    merge_near_lists,
    min_target_area,
    zone_for,
)


def test_kitchen_near_dining_in_near_list():
    near = merge_near_lists([], "厨房")
    assert "餐厅" in near


def test_min_target_area_for_small_rooms():
    assert min_target_area("厨房") >= 5.0
    assert min_target_area("卫生间") >= 3.5


def test_default_bands_order_private_before_kitchen():
    bands = build_default_bands(
        public_types=["客厅", "餐厅", "阳台"],
        private_types=["主卧", "次卧"],
        service_types=["卫生间", "厨房"],
    )
    assert len(bands) >= 2
    flat = [r for band in bands for r in band]
    assert flat.index("主卧") < flat.index("厨房")
    assert "阳台" in flat


def test_zone_for_living_south():
    assert zone_for("客厅") == "south"
    assert zone_for("主卧") == "north"
