from urllib.parse import quote

from app.agents.prompts import build_drawer_image_prompt
from app.schemas.drawer import DrawerDraft, ValidationResult
from app.schemas.planner import PlannerFinalPlan


class DrawerAgent:
    """
    规则回退模式：
    - 不生成矢量坐标
    - 返回占位图片 URL 与绘图提示词
    """

    def run(self, plan: PlannerFinalPlan) -> DrawerDraft:
        prompt = build_drawer_image_prompt(plan)
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
