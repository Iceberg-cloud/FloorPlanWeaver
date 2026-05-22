import re
from app.schemas.planner import (
    PlannerAskForMore,
    PlannerFinalPlan,
    ProjectProfile,
    HouseholdProfile,
    OwnerSummary,
    RoomAreaRow,
    AreaValidation,
    SpaceProgramItem,
    AdjacencyRule,
)

# ── Room area templates (㎡) based on layout type ──
ROOM_TEMPLATES: dict[str, dict[str, dict]] = {
    "一居": {
        "客厅": {"area": 22, "notes": "客餐厅一体"},
        "主卧": {"area": 16, "notes": ""},
        "厨房": {"area": 7, "notes": "紧凑型"},
        "卫生间": {"area": 5, "notes": "干湿分离"},
        "阳台": {"area": 5, "notes": ""},
    },
    "两居": {
        "客厅": {"area": 24, "notes": ""},
        "餐厅": {"area": 10, "notes": "靠近厨房"},
        "主卧": {"area": 16, "notes": "可带独卫"},
        "次卧": {"area": 12, "notes": ""},
        "厨房": {"area": 8, "notes": ""},
        "卫生间": {"area": 5, "notes": "干湿分离", "count": 1},
        "阳台": {"area": 6, "notes": "连接客厅"},
    },
    "三居": {
        "客厅": {"area": 26, "notes": "核心公共空间"},
        "餐厅": {"area": 12, "notes": "靠近厨房"},
        "主卧": {"area": 18, "notes": "可带独卫"},
        "次卧": {"area": 12, "notes": "", "count": 2},
        "厨房": {"area": 9, "notes": ""},
        "卫生间": {"area": 5, "notes": "干湿分离", "count": 2},
        "阳台": {"area": 6, "notes": "连接客厅"},
    },
    "四居": {
        "客厅": {"area": 30, "notes": "大开间"},
        "餐厅": {"area": 14, "notes": "可兼做会客"},
        "主卧": {"area": 20, "notes": "套间设计"},
        "次卧": {"area": 14, "notes": "", "count": 2},
        "书房": {"area": 10, "notes": "可兼做客房"},
        "厨房": {"area": 10, "notes": ""},
        "卫生间": {"area": 5, "notes": "干湿分离", "count": 2},
        "阳台": {"area": 8, "notes": "大阳台连接客厅"},
    },
}

# ── Default adjacency rules ──
DEFAULT_ADJACENCY = [
    AdjacencyRule(source="厨房", target="餐厅", relation="required", description="备餐动线最短"),
    AdjacencyRule(source="主卧", target="卫生间", relation="preferred", description="方便夜间使用"),
    AdjacencyRule(source="客厅", target="阳台", relation="preferred", description="延伸公共空间"),
    AdjacencyRule(source="入户门", target="客厅", relation="required", description="归家第一空间"),
    AdjacencyRule(source="主卧", target="客厅", relation="preferred", description="避免穿行"),
]


_LAYOUT_DEFAULT_AREA = {"一居": 45, "两居": 75, "三居": 100, "四居": 140}


class PlannerAgent:
    REQUIRED_KEYS = [
        "building_type",
        "target_area_sqm",
        "layout_type",
        "room_program",
        "orientation",
    ]

    def run(
        self,
        user_message: str,
        collected: dict,
        *,
        force_finalize: bool = False,
        ask_count: int = 0,
    ) -> PlannerAskForMore | PlannerFinalPlan:
        from app.core.config import settings

        merged = dict(collected)
        self._extract_to_collected(user_message, merged)

        if (
            force_finalize
            or ask_count >= settings.planner_max_ask_rounds
            or self._ready_for_plan(merged)
        ):
            self._apply_defaults(merged)
            return self._build_final_plan(merged)

        missing = [key for key in self.REQUIRED_KEYS if key not in merged or not merged[key]]
        if missing:
            return PlannerAskForMore(
                agent_state="ASK_FOR_MORE",
                missing_fields=missing[:2],
                follow_up_questions=self._build_questions(missing, merged),
                collected_snapshot=merged,
            )

        self._apply_defaults(merged)
        return self._build_final_plan(merged)

    def _apply_defaults(self, collected: dict) -> None:
        if not collected.get("building_type"):
            collected["building_type"] = "住宅"
        if not collected.get("layout_type"):
            collected["layout_type"] = "三居"
        layout = collected["layout_type"]
        if not collected.get("target_area_sqm"):
            collected["target_area_sqm"] = _LAYOUT_DEFAULT_AREA.get(layout, 90)
        if not collected.get("orientation"):
            collected["orientation"] = "南向优先"
        if not collected.get("room_program") and layout in ROOM_TEMPLATES:
            collected["room_program"] = self._template_room_list(layout)

    def _template_room_list(self, layout_type: str) -> list[dict]:
        tmpl = ROOM_TEMPLATES.get(layout_type, ROOM_TEMPLATES["三居"])
        rooms: list[dict] = []
        for rt, spec in tmpl.items():
            count = int(spec.get("count", 1))
            rooms.append({
                "room_type": rt,
                "count": count,
                "target_area_sqm": float(spec.get("area", 10)),
                "notes": spec.get("notes", ""),
            })
        return rooms

    def _ready_for_plan(self, collected: dict) -> bool:
        """User gave enough signal — skip further questions and finalize."""
        if collected.get("room_program"):
            return True
        if collected.get("layout_type"):
            return True
        if collected.get("target_area_sqm"):
            return True
        return False

    def _build_final_plan(self, merged: dict) -> PlannerFinalPlan:
        layout_type = merged.get("layout_type", "三居")
        target_area = float(merged.get("target_area_sqm", 100))
        orientation = merged.get("orientation", "南向优先")
        building_type = merged.get("building_type", "住宅")
        user_prefs = merged.get("user_preferences") or []

        # Build room program from template or user input
        room_program_raw = merged.get("room_program", [])
        space_program = self._build_space_program(room_program_raw, layout_type, target_area)

        # Build adjacency from user input + defaults
        adjacency_raw = merged.get("adjacency_rules", [])
        adjacency = self._build_adjacency(adjacency_raw)

        # Build circulation
        circulation = self._build_circulation(layout_type, space_program)

        # Build zoning
        zoning = self._build_zoning(space_program)

        # Build area validation
        area_val = self._validate_areas(space_program, target_area)

        # Build owner summary
        owner_summary = self._build_owner_summary(
            building_type, layout_type, target_area, orientation,
            space_program, circulation, zoning, adjacency, area_val,
        )

        # Build drawing brief
        drawing_brief = self._build_drawing_brief(
            layout_type, target_area, orientation, space_program, circulation,
            user_preferences=user_prefs,
        )

        # Build design goals from preferences
        design_goals = self._build_design_goals(target_area, orientation, user_prefs)

        return PlannerFinalPlan(
            agent_state="FINAL_PLAN",
            project_profile=ProjectProfile(
                building_type=building_type,
                target_area_sqm=target_area,
                layout_type=layout_type,
                orientation=orientation,
            ),
            design_goals=design_goals,
            space_program=space_program,
            adjacency_graph=adjacency,
            circulation=circulation,
            openings_strategy={
                "entrance": "入户门设置玄关缓冲区，避免直视客厅",
                "windows": f"主要居住空间优先{orientation}开窗",
                "balcony": "阳台优先连接客厅，兼顾晾晒与休闲",
                "interior": "卫生间与厨房优先利用间接采光或通风井",
            },
            orientation_daylighting={
                "primary_living_face": orientation,
                "notes": "客厅与主卧优先布置于采光较好一侧；次卧、书房可布置于北侧",
            },
            zoning=zoning,
            drawing_brief=drawing_brief,
            change_summary=[],
            household_profile=HouseholdProfile(
                description=f"{building_type}，{layout_type}，{target_area}㎡，{orientation}",
            ),
            lifestyle_tags=["标准居住"] + user_prefs[:3],
            owner_summary=owner_summary,
        )

    def _build_space_program(
        self, user_rooms: list, layout_type: str, target_area: float,
    ) -> list[SpaceProgramItem]:
        template = ROOM_TEMPLATES.get(layout_type, ROOM_TEMPLATES["三居"])

        if user_rooms:
            # Use user-provided rooms, fill defaults from template
            items = []
            for r in user_rooms:
                rt = r.get("room_type", "")
                tmpl = template.get(rt, {})
                items.append(SpaceProgramItem(
                    room_type=rt,
                    count=int(r.get("count", 1)),
                    target_area_sqm=float(r.get("target_area_sqm") or tmpl.get("area", 10)),
                    notes=str(r.get("notes", "") or tmpl.get("notes", "")),
                ))
            return items

        # Use template, scale to target area
        template_total = sum(t["area"] * t.get("count", 1) for t in template.values())
        scale = target_area / template_total if template_total > 0 else 1.0

        items = []
        for rt, t in template.items():
            area = round(t["area"] * scale, 1)
            items.append(SpaceProgramItem(
                room_type=rt,
                count=t.get("count", 1),
                target_area_sqm=area,
                notes=t.get("notes", ""),
            ))
        return items

    def _build_adjacency(self, raw: list) -> list[AdjacencyRule]:
        rules = []
        for r in raw:
            rules.append(AdjacencyRule(
                source=r.get("source", ""),
                target=r.get("target", ""),
                relation=r.get("relation", "preferred"),
                description=r.get("description", ""),
            ))
        # Add defaults that don't conflict
        existing_pairs = {(r.source, r.target) for r in rules}
        for d in DEFAULT_ADJACENCY:
            if (d.source, d.target) not in existing_pairs and (d.target, d.source) not in existing_pairs:
                rules.append(d)
        return rules

    def _build_circulation(self, layout_type: str, program: list[SpaceProgramItem]) -> dict:
        room_names = {p.room_type for p in program}
        main_route = "入户 → 玄关 → 客厅"
        if "餐厅" in room_names:
            main_route += " → 餐厅"
        if "厨房" in room_names:
            main_route += " / 厨房"
        main_route += " → 卧室区"

        secondary = []
        if "阳台" in room_names:
            secondary.append("客厅 ↔ 阳台（生活与休闲）")
        if "厨房" in room_names and "餐厅" in room_names:
            secondary.append("厨房 ↔ 餐厅（备餐动线）")
        secondary.append("卫生间与卧室就近可达")

        bedroom_zone = "、".join(
            n for n in ("主卧", "次卧", "卧室", "儿童房") if n in room_names
        ) or "卧室区"
        return {
            "main_route": main_route,
            "secondary_routes": secondary,
            "principle": (
                "动静分离：公共动线不穿越私密区；"
                f"私密区（{bedroom_zone}）宜靠内；卫生间/阳台靠边布置"
            ),
            "bedroom_access": f"{bedroom_zone} 宜通过走廊或客厅过渡到达，避免穿行厨房",
            "service_access": "卫生间宜邻近卧室或走廊，避免门对餐厅/客厅",
        }

    def _build_zoning(self, program: list[SpaceProgramItem]) -> dict:
        public_types = {"客厅", "餐厅", "厨房", "玄关", "阳台"}
        private_types = {"主卧", "次卧", "书房", "儿童房"}
        service_types = {"卫生间", "储物间", "洗衣房"}

        public = [p.room_type for p in program if p.room_type in public_types]
        private = [p.room_type for p in program if p.room_type in private_types]
        service = [p.room_type for p in program if p.room_type in service_types]
        other = [p.room_type for p in program if p.room_type not in public_types | private_types | service_types]

        return {
            "public_zone": public,
            "private_zone": private,
            "service_zone": service,
            "other": other,
            "principle": "公共区靠入口，私密区靠内侧，服务区穿插其间",
        }

    def _validate_areas(self, program: list[SpaceProgramItem], target: float) -> AreaValidation:
        planned = sum(p.target_area_sqm * p.count for p in program)
        deviation = ((planned - target) / target * 100) if target > 0 else 0
        passed = abs(deviation) <= 10
        if deviation > 10:
            msg = f"规划总面积{planned:.1f}㎡超出目标{target}㎡（+{deviation:.1f}%），建议缩减非核心空间"
        elif deviation < -10:
            msg = f"规划总面积{planned:.1f}㎡低于目标{target}㎡（{deviation:.1f}%），建议增大公共空间"
        else:
            msg = f"面积规划合理（偏差{deviation:+.1f}%）"
        return AreaValidation(
            target_total_sqm=target,
            planned_total_sqm=round(planned, 1),
            deviation_percent=round(deviation, 1),
            passed=passed,
            message=msg,
        )

    def _build_owner_summary(
        self, building_type, layout_type, target_area, orientation,
        program, circulation, zoning, adjacency, area_val,
    ) -> OwnerSummary:
        room_rows = [
            RoomAreaRow(
                room_type=p.room_type,
                count=p.count,
                area_sqm=p.target_area_sqm,
                ratio_percent=round(p.target_area_sqm * p.count / target_area * 100, 1) if target_area > 0 else 0,
            )
            for p in program
        ]
        return OwnerSummary(
            headline=f"{building_type} · {layout_type} · {target_area}㎡ · {orientation}",
            room_rows=room_rows,
            circulation_text=circulation.get("main_route", ""),
            zoning_text=f"公共区：{'+'.join(zoning.get('public_zone', []))}；私密区：{'+'.join(zoning.get('private_zone', []))}",
            adjacency_text="；".join(f"{a.source}↔{a.target}({a.relation})" for a in adjacency[:5]),
            daylight_text=f"主要采光面：{orientation}",
            area_validation=area_val,
        )

    def _build_drawing_brief(
        self, layout_type, target_area, orientation, program, circulation,
        *, user_preferences: list[str] | None = None,
    ) -> str:
        room_specs = "、".join(
            f"{p.room_type}{p.count}间({p.target_area_sqm}㎡)" for p in program
        )
        brief = (
            f"{layout_type}住宅，目标{target_area}㎡，{orientation}。\n"
            f"房间配置：{room_specs}。\n"
            f"动线：{circulation.get('main_route', '')}。\n"
            f"公共空间位于入口侧，私密空间靠内侧。"
        )
        if user_preferences:
            brief += f"\n用户偏好：{'、'.join(user_preferences[:8])}。"
        return brief

    def _build_design_goals(self, target_area: float, orientation: str, user_prefs: list[str]) -> list[str]:
        goals = [
            "满足核心居住功能，优化采光与通风",
            "保证公共与私密空间分区合理，动静分离",
            "优先满足用户关键邻接关系偏好",
            f"总建筑面积控制在{target_area}㎡附近，误差不超过5%",
        ]
        pref_text = "、".join(user_prefs[:5])
        if pref_text:
            goals.append(f"满足用户特殊要求：{pref_text}")
        return goals

    # ── Modification intent detection ────────────────────────────
    # Patterns indicating the user is giving a *modification* instruction
    # rather than describing a *new* room list.
    _MODIFICATION_PATTERN = re.compile(
        r"(请|把|将|让|要|希望|能不能|可以|能否).*?"
        r"(移动|移到|移至|搬到|换|改|调整|增大|缩小|删除|去掉|放到|安排到|调到|变|换成|替换)"
        r"|(不要|去掉|删除|取消).{0,6}(房间|卧室|厨房|卫生间|阳台|客厅|餐厅|书房)"
        r"|(移动|移到|移至|搬到|放到|安排到|调到).{0,10}(左|右|上|下|角|边|侧)"
        r"|(改|调整|换).{0,6}(一下|一个|到|至|去)?"
    )

    def _extract_to_collected(self, text: str, collected: dict) -> None:
        if any(word in text for word in ["住宅", "公寓", "别墅", "户型", "房子", "房"]):
            if "别墅" in text:
                collected["building_type"] = "别墅"
            elif "公寓" in text:
                collected["building_type"] = "公寓"
            else:
                collected["building_type"] = "住宅"

        area_match = re.search(r"(\d+)\s*(平|平方|㎡|m2|平⽶)", text)
        if area_match:
            collected["target_area_sqm"] = int(area_match.group(1))

        if "一居" in text or "一室" in text:
            collected["layout_type"] = "一居"
        elif any(w in text for w in ["两居", "二居", "两室", "二室"]):
            collected["layout_type"] = "两居"
        elif "三居" in text or "三室" in text:
            collected["layout_type"] = "三居"
        elif "四居" in text or "四室" in text:
            collected["layout_type"] = "四居"

        if any(word in text for word in ["朝南", "南向", "南北通透", "采光", "通透"]):
            collected["orientation"] = "南向优先"
        elif "朝北" in text:
            collected["orientation"] = "北向"
        elif "朝东" in text:
            collected["orientation"] = "东向"
        elif "朝西" in text:
            collected["orientation"] = "西向"

        rooms = []
        room_map = {
            "客厅": 24, "餐厅": 12, "厨房": 9,
            "主卧": 18, "次卧": 12, "卧室": 14, "书房": 10,
            "卫生间": 5, "阳台": 6, "玄关": 4,
            "储物间": 3, "衣帽间": 4, "儿童房": 12,
            "起居室": 20, "客餐厅": 22,
        }
        is_modification = bool(self._MODIFICATION_PATTERN.search(text))
        # Track matched positions to avoid duplicate matching (e.g. "客餐厅" contains "餐厅")
        matched_spans: list[tuple[int, int]] = []

        # First pass: match longer/compound names first to avoid partial matches
        sorted_names = sorted(room_map.keys(), key=len, reverse=True)
        for name in sorted_names:
            default_area = room_map[name]
            start = 0
            while True:
                idx = text.find(name, start)
                if idx == -1:
                    break
                # Check if this span overlaps with already matched span
                end_idx = idx + len(name)
                overlaps = any(s <= idx < e or s < end_idx <= e for s, e in matched_spans)
                if not overlaps:
                    matched_spans.append((idx, end_idx))
                    area_match = re.search(rf"{name}.*?(\d+)\s*㎡", text)
                    area = int(area_match.group(1)) if area_match else default_area
                    count = 1
                    if name == "次卧":
                        if "两次卧" in text or "两个次卧" in text or "2个次卧" in text:
                            count = 2
                    if name == "卧室":
                        if "两卧室" in text or "两个卧室" in text or "2个卧室" in text or "双卧室" in text:
                            count = 2
                    if name == "卫生间":
                        if (
                            "两卫" in text or "双卫" in text or "2卫" in text
                            or "两个卫生间" in text or "两间卫生间" in text or "2个卫生间" in text
                        ):
                            count = 2
                    rooms.append({"room_type": name, "count": count, "target_area_sqm": area, "notes": ""})
                start = idx + 1
        if rooms:
            existing_rooms = collected.get("room_program") or []
            if is_modification and existing_rooms:
                # Modification intent: merge with existing, don't replace
                # Also inject position hints into existing room notes
                self._inject_position_hints(text, existing_rooms, rooms)
                collected["room_program"] = self._merge_room_extracts(existing_rooms, rooms)
            else:
                # New description: replace room_program
                collected["room_program"] = rooms

        adjacency = []
        if "厨房和餐厅" in text or ("厨房" in text and "餐厅" in text):
            adjacency.append({"source": "厨房", "target": "餐厅", "relation": "required", "description": "便于备餐动线"})
        if "主卧带独卫" in text or "主卧带卫生间" in text or "套间" in text:
            adjacency.append({"source": "主卧", "target": "卫生间", "relation": "required", "description": "套间关系"})
        if "客厅朝南" in text or "客厅南向" in text:
            adjacency.append({"source": "客厅", "target": "南侧外墙", "relation": "required", "description": "保证采光"})
        if "动静分离" in text:
            adjacency.append({"source": "客厅", "target": "卧室区", "relation": "required", "description": "动静分区"})
        if adjacency:
            collected["adjacency_rules"] = adjacency

    @staticmethod
    def _merge_room_extracts(existing: list[dict], new_mentions: list[dict]) -> list[dict]:
        """Merge newly mentioned rooms into existing room_program.

        - If a room type already exists in `existing`, keep the existing entry.
        - Only add rooms that don't exist yet (user is adding new rooms).
        """
        existing_types = {r.get("room_type") for r in existing if isinstance(r, dict)}
        merged = list(existing)
        for r in new_mentions:
            if isinstance(r, dict) and r.get("room_type") not in existing_types:
                merged.append(r)
        return merged

    @staticmethod
    def _inject_position_hints(text: str, existing_rooms: list[dict], mentioned_rooms: list[dict]) -> None:
        """When user gives a modification with position info, inject it into room notes.

        E.g. "将厨房移到右下角" → kitchen room gets notes="用户要求：右下角"
        """
        # Map direction keywords to position labels
        position_map = {
            "右下": "右下角", "左下": "左下角", "右上": "右上角", "左上": "左上角",
            "下方": "下方", "上方": "上方", "左侧": "左侧", "右侧": "右侧",
            "中间": "中间", "中心": "中心",
            "南": "南侧", "北": "北侧", "东": "东侧", "西": "西侧",
        }
        detected_pos = None
        for kw, label in position_map.items():
            if kw in text:
                detected_pos = label
                break
        if not detected_pos:
            return

        mentioned_types = {r.get("room_type") for r in mentioned_rooms if isinstance(r, dict)}
        for room in existing_rooms:
            if not isinstance(room, dict):
                continue
            if room.get("room_type") in mentioned_types:
                room["notes"] = f"用户要求：{detected_pos}" + (f"；{room['notes']}" if room.get("notes") else "")

    def _build_questions(self, missing_fields: list[str], collected: dict) -> list[str]:
        """At most 2 short questions per round."""
        priority = ("layout_type", "target_area_sqm", "room_program", "orientation", "building_type")
        ordered = [f for f in priority if f in missing_fields]
        ordered += [f for f in missing_fields if f not in ordered]

        if "layout_type" in ordered and "target_area_sqm" in ordered:
            return [
                "请补充户型类型与建筑面积（例如：三居、约120㎡）；朝向与房间若有要求可一并说明。",
            ]

        mapping = {
            "building_type": "请确认建筑类型（住宅/公寓/别墅）？",
            "target_area_sqm": "请确认总建筑面积（例如 120㎡）？",
            "layout_type": "请确认户型（如一居/两居/三居）？",
            "room_program": "请简要说明需要哪些房间（如三卧两卫、阳台）？",
            "orientation": "是否有朝向偏好（如南向）？",
        }
        built = [mapping[f] for f in ordered[:2] if f in mapping]
        if built:
            return built
        return ["请补充户型类型、建筑面积与房间需求（例如：三居、约120㎡）。"]
