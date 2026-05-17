import re

from app.schemas.planner import PlannerAskForMore, PlannerFinalPlan, ProjectProfile


class PlannerAgent:
    REQUIRED_KEYS = [
        "building_type",
        "target_area_sqm",
        "layout_type",
        "room_program",
        "adjacency_rules",
        "orientation",
    ]

    def run(self, user_message: str, collected: dict) -> PlannerAskForMore | PlannerFinalPlan:
        merged = dict(collected)
        self._extract_to_collected(user_message, merged)
        missing = [key for key in self.REQUIRED_KEYS if key not in merged or not merged[key]]

        if missing:
            return PlannerAskForMore(
                agent_state="ASK_FOR_MORE",
                missing_fields=missing,
                follow_up_questions=self._build_questions(missing),
                collected_snapshot=merged,
            )

        return PlannerFinalPlan(
            agent_state="FINAL_PLAN",
            project_profile=ProjectProfile(
                building_type=merged["building_type"],
                target_area_sqm=float(merged["target_area_sqm"]),
                layout_type=merged["layout_type"],
                orientation=merged["orientation"],
            ),
            design_goals=[
                "满足核心居住功能并优化采光",
                "保证公共与私密空间分区合理",
                "优先满足用户关键邻接关系偏好",
            ],
            space_program=merged["room_program"],
            adjacency_graph=merged["adjacency_rules"],
            circulation={
                "main_route": "入户->客餐厅->卧室区",
                "secondary_route": "客餐厅->厨房/阳台",
            },
            openings_strategy={
                "entrance": "入户门设置玄关缓冲",
                "windows": "主要居住空间优先南向开窗",
                "balcony": "阳台优先连接客厅",
            },
            orientation_daylighting={
                "primary_living_face": merged["orientation"],
                "notes": "客厅与主卧优先布置于采光较好一侧",
            },
            zoning={
                "public_zone": ["客厅", "餐厅", "厨房"],
                "private_zone": ["主卧", "次卧", "书房"],
            },
            drawing_brief=(
                "外轮廓近似矩形，客厅位于中心偏南，餐厅靠近客厅与厨房，"
                "主卧尽量带独卫，门窗与交通动线保持可达。"
            ),
            change_summary=[],
        )

    def _extract_to_collected(self, text: str, collected: dict) -> None:
        if any(word in text for word in ["住宅", "公寓", "别墅", "户型"]):
            if "别墅" in text:
                collected["building_type"] = "别墅"
            elif "公寓" in text:
                collected["building_type"] = "公寓"
            else:
                collected["building_type"] = "住宅"

        area_match = re.search(r"(\d+)\s*(平|平方|㎡|m2)", text)
        if area_match:
            collected["target_area_sqm"] = int(area_match.group(1))

        if "一居" in text:
            collected["layout_type"] = "一居"
        elif "两居" in text or "二居" in text:
            collected["layout_type"] = "两居"
        elif "三居" in text:
            collected["layout_type"] = "三居"
        elif "四居" in text:
            collected["layout_type"] = "四居"

        if any(word in text for word in ["朝南", "南向", "南北通透", "采光"]):
            collected["orientation"] = "南向优先"

        rooms = []
        if "客厅" in text:
            rooms.append({"room_type": "客厅", "count": 1, "target_area_sqm": 26, "notes": ""})
        if "餐厅" in text:
            rooms.append({"room_type": "餐厅", "count": 1, "target_area_sqm": 14, "notes": ""})
        if "厨房" in text:
            rooms.append({"room_type": "厨房", "count": 1, "target_area_sqm": 10, "notes": ""})
        if "主卧" in text:
            rooms.append({"room_type": "主卧", "count": 1, "target_area_sqm": 18, "notes": "可带独卫"})
        if "次卧" in text:
            rooms.append({"room_type": "次卧", "count": 2, "target_area_sqm": 12, "notes": ""})
        if "卫生间" in text or "两卫" in text:
            count = 2 if "两卫" in text or "双卫" in text else 1
            rooms.append({"room_type": "卫生间", "count": count, "target_area_sqm": 5, "notes": ""})
        if "阳台" in text:
            rooms.append({"room_type": "阳台", "count": 1, "target_area_sqm": 6, "notes": ""})
        if rooms:
            collected["room_program"] = rooms

        adjacency = []
        if "厨房和餐厅靠近" in text or ("厨房" in text and "餐厅" in text and "靠近" in text):
            adjacency.append(
                {"source": "厨房", "target": "餐厅", "relation": "required", "description": "便于备餐动线"}
            )
        if "主卧带独卫" in text:
            adjacency.append(
                {"source": "主卧", "target": "主卫", "relation": "required", "description": "套间关系"}
            )
        if "客厅朝南" in text:
            adjacency.append(
                {"source": "客厅", "target": "南侧外墙", "relation": "preferred", "description": "保证采光"}
            )
        if adjacency:
            collected["adjacency_rules"] = adjacency

    def _build_questions(self, missing_fields: list[str]) -> list[str]:
        mapping = {
            "building_type": "请确认建筑类型（住宅/公寓/别墅/单层）？",
            "target_area_sqm": "请确认总建筑面积（例如 120㎡）？",
            "layout_type": "请确认户型类型（如三居/四居）？",
            "room_program": "请列出希望包含的房间及数量（如三卧两卫）？",
            "adjacency_rules": "是否有必须相邻或必须分离的空间关系？",
            "orientation": "是否有朝向偏好（如客厅朝南、南北通透）？",
        }
        return [mapping[item] for item in missing_fields if item in mapping]
