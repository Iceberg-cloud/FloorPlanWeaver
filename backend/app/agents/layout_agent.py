"""Layout Agent: semantic zones/bands only — coordinates compiled server-side."""
from __future__ import annotations
from app.schemas.layout import Point2D
from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import AdjacencyIntent, LayoutBand, RoomPlacement, SemanticLayoutPlan


SEMANTIC_LAYOUT_SYSTEM_PROMPT = """你是住宅户型分区顾问。你输出「房间大致位置与相对大小」的 JSON（归一化比例，非绝对米制坐标）。

## 输出要求
- 严格 JSON，符合 SemanticLayoutPlan 结构
- layout_style="strip"，strip_direction 为 horizontal 或 vertical
- bands：每个 band 的 order 表示条带内从左到右（horizontal）或从下到上（vertical）的房间顺序
- placements 中每个房间必须包含：
  - zone, size, cluster, index（多实例时 index=1,2,...）
  - center_x, center_y：在外轮廓包围盒内的归一化中心（0~1，左/下为0，右/上为1）
  - width_ratio, height_ratio：该房间约占外轮廓宽/高的比例（0.05~1，各房间之和可大于1但应合理）
- 不得输出绝对坐标 x/y、polygon、area_sqm

## 布置原则（与编译器一致）
- 覆盖用户房间清单中的每个 room_type
- 布置优先级：① 卫生间/阳台/卧室 ② 厨房 ③ 客厅与餐厅划分剩余大区
- 相邻房间 center 应接近；公共区靠入口侧（center_y 偏小）
- 客厅/餐厅 width_ratio、height_ratio 宜大；卫生间/阳台宜小且靠边
- adjacency_intent：厨房-餐厅 must；卫生间-厨房 avoid
- 只输出 JSON"""


def build_layout_prompt(plan, outline_vertices, entrance_edge, outline_area, *, validation_errors=None):
    parts = [
        "## 说明",
        "以下为用户最新确认的设计方案（FINAL_PLAN），矢量布置必须以此为准，不得遗漏房间或擅自改面积档位。",
    ]
    profile = plan.project_profile
    parts.append(
        f"\n## 项目画像\n"
        f"- 类型：{profile.building_type} · {profile.layout_type} · 约{profile.target_area_sqm}㎡\n"
        f"- 朝向：{profile.orientation}"
    )
    if plan.design_goals:
        parts.append("- 设计目标：" + "；".join(plan.design_goals))
    verts_str = " → ".join(f"({v.x:.1f}, {v.y:.1f})" for v in outline_vertices)
    parts.append(f"\n## 建筑外轮廓\n顶点：\n{verts_str}")
    parts.append(f"入口边索引：{entrance_edge}")
    parts.append(f"总面积：{outline_area:.1f} 平方米")
    parts.append("\n## 房间需求（最新 space_program）")
    for item in plan.space_program:
        notes = f"，{item.notes}" if getattr(item, "notes", None) else ""
        parts.append(f"- {item.room_type} x{item.count}（目标 {item.target_area_sqm}㎡{notes}）")
    if plan.adjacency_graph:
        parts.append("\n## 邻接关系")
        for edge in plan.adjacency_graph:
            parts.append(
                f"- {edge.source} → {edge.target}（{edge.relation}）"
                + (f"：{edge.description}" if edge.description else "")
            )
    circ = plan.circulation or {}
    if circ.get("main_route"):
        parts.append(f"\n## 动线\n主路径：{circ.get('main_route')}")
    if plan.drawing_brief:
        parts.append(f"\n## 绘图摘要（最新）\n{plan.drawing_brief}")
    if validation_errors:
        parts.append("\n## 上次校验问题")
        for err in validation_errors:
            parts.append(f"- {err}")
    parts.append(
        "\n请输出 SemanticLayoutPlan JSON（每个 placement 含 center_x/center_y/width_ratio/height_ratio）。"
    )
    return "\n".join(parts)


def parse_semantic_json(raw):
    placements = [RoomPlacement.model_validate(p) for p in raw.get("placements", [])]
    bands = [LayoutBand.model_validate(b) for b in raw.get("bands", [])]
    adjacency = [AdjacencyIntent.model_validate(a) for a in raw.get("adjacency_intent", [])]
    return SemanticLayoutPlan(
        layout_style=raw.get("layout_style", "strip"),
        strip_direction=raw.get("strip_direction", "horizontal"),
        public_side=raw.get("public_side", "south"),
        entrance_room=raw.get("entrance_room", ""),
        placements=placements, bands=bands, adjacency_intent=adjacency,
    )
