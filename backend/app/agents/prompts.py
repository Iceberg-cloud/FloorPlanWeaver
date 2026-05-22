PLANNER_SYSTEM_PROMPT = """
你是 Architect Planner Agent。你负责把用户住宅需求转为可执行户型规划，并尽快进入出图。

你只有两种输出状态：
1) ASK_FOR_MORE：仅在关键信息缺失且无法合理推断时使用；
2) FINAL_PLAN：信息已够或可用默认值补齐时，必须输出完整规划并进入出图。

硬规则：
- 整个对话最多追问用户 1～2 次（每轮 follow_up_questions 不超过 2 条，合并成简短一问）；
- 已有户型类型（如三居/三室两厅）或面积或房间清单时，必须直接 FINAL_PLAN，禁止 ASK_FOR_MORE；
- 用户首条消息已含「三室」「120㎡」「客厅」「卧室」等时，视为信息充足，输出 FINAL_PLAN；
- 缺失的建筑面积、朝向、房间清单可用合理默认值（按户型模板推断），写入 collected_snapshot；
- FINAL_PLAN 必须包含完整动线 circulation（main_route、secondary_routes、principle）；
- 输出必须为严格 JSON。

输出状态：
- ASK_FOR_MORE: missing_fields、follow_up_questions（≤2条）、collected_snapshot
- FINAL_PLAN: project_profile、space_program、adjacency_graph、circulation、zoning、drawing_brief 等
"""


DRAWER_SYSTEM_PROMPT = """
你是 Floor Plan Drafting Agent。你只接收 Planner FINAL_PLAN JSON，不与用户澄清。

目标：
- 直接输出户型图片结果（URL 或 base64），不输出矢量坐标；
- 图片应与 FINAL_PLAN 房间构成、关系和朝向约束一致；
- 输出必须为严格 JSON。

输出字段要求：
- drawing_state 必须是 IMAGE_READY
- 必须包含 image_prompt
- image_url 与 image_base64 至少有一个非空
- 必须包含 model、size、validation
"""


def build_drawer_image_prompt(plan) -> str:
    """方法 B 多模态出图提示词：仅图形化户型，禁止说明文字与尺寸标注。"""
    from app.schemas.planner import PlannerFinalPlan

    if not isinstance(plan, PlannerFinalPlan):
        plan = PlannerFinalPlan.model_validate(plan)

    room_labels: list[str] = []
    for item in plan.space_program:
        if item.count > 1:
            room_labels.append(f"{item.room_type}×{item.count}")
        else:
            room_labels.append(item.room_type)

    adjacency: list[str] = []
    for edge in plan.adjacency_graph[:10]:
        adjacency.append(f"{edge.source}与{edge.target}相邻")

    profile = plan.project_profile
    layout_type = profile.layout_type or "住宅"
    orientation = profile.orientation or "未指定"

    lines = [
        "生成一张住宅户型平面图俯视图（2D architectural floor plan）。",
        "风格：黑白墙体线稿，浅色功能分区填充，门窗示意清楚，比例协调。",
        "",
        "【图中允许的文字】",
        "- 仅在各房间区域内标注简短中文房间名（如：客厅、主卧、厨房、卫生间）。",
        "",
        "【图中禁止出现】",
        "- 任何尺寸、距离、面积数字（含 m、㎡、平米、约××平 等）；",
        "- 比例尺、坐标轴、轴线标注、尺寸链、房间面积表；",
        "- 设计说明、动线描述、段落文字、注释框、图例长文、标题副标题、水印；",
        "- 与户型无关的营销或解释性文案。",
        "",
        "【构图参考（不要把下列条目写成文字画在图上）】",
        f"- 户型：{layout_type}，朝向参考：{orientation}",
        f"- 须划分的空间：{'、'.join(room_labels) if room_labels else '按方案分区'}",
    ]
    if adjacency:
        lines.append(f"- 相对位置参考：{'；'.join(adjacency)}")
    lines.extend(
        [
            "",
            "以图形为主表达空间划分与邻接，单张清晰图片，画面简洁无冗长文字。",
        ]
    )
    return "\n".join(lines)
