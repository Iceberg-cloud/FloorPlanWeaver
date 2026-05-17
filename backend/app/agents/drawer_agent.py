from urllib.parse import quote

from app.schemas.drawer import DrawerDraft, ValidationResult
from app.schemas.planner import PlannerFinalPlan


class DrawerAgent:
    """
    规则回退模式：
    - 不生成矢量坐标
    - 返回占位图片 URL 与绘图提示词
    """

    def run(self, plan: PlannerFinalPlan) -> DrawerDraft:
        room_lines = []
        for item in plan.space_program:
            suffix = f"约{item.target_area_sqm}㎡" if item.target_area_sqm else "面积自适应"
            room_lines.append(f"{item.room_type}x{item.count}（{suffix}）")
        prompt = (
            "生成一张现代住宅平面图俯视图，黑白线稿风格，标注中文房间名。"
            f"户型需求：{'; '.join(room_lines)}。"
            f"关系约束：{plan.drawing_brief}。"
            "要求比例协调、走线清晰、墙体与门窗表达明确。"
        )
        placeholder = (
            "https://placehold.co/1024x1024/png?text="
            + quote("Image Model Failed - Rule Fallback")
        )

        return DrawerDraft(
            drawing_state="IMAGE_READY",
            image_url=placeholder,
            image_prompt=prompt,
            model="rule-fallback",
            size="1024x1024",
            validation=ValidationResult(
                hard_constraints_passed=False,
                notes=["当前为规则回退占位图，不代表真实模型生成结果。"],
            ),
        )
