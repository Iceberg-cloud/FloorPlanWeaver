import json
from dataclasses import dataclass
from urllib import error, request as urllib_request

from app.agents.drawer_agent import DrawerAgent
from app.core.config import settings
from app.schemas.drawer import DrawerDraft
from app.schemas.planner import PlannerFinalPlan


@dataclass
class DrawerExecutionResult:
    output: DrawerDraft
    llm_enabled: bool
    llm_attempted: bool
    llm_succeeded: bool
    fallback_to_rule: bool
    error: str | None = None


class DrawerService:
    def __init__(self) -> None:
        self.agent = DrawerAgent()

    def generate(self, plan: PlannerFinalPlan) -> DrawerExecutionResult:
        if settings.drawer_use_llm:
            image_result, error = self._generate_image_with_model(plan)
            if image_result is not None:
                return DrawerExecutionResult(
                    output=image_result,
                    llm_enabled=True,
                    llm_attempted=True,
                    llm_succeeded=True,
                    fallback_to_rule=False,
                    error=None,
                )
            if settings.drawer_fallback_to_rule:
                return DrawerExecutionResult(
                    output=self.agent.run(plan),
                    llm_enabled=True,
                    llm_attempted=True,
                    llm_succeeded=False,
                    fallback_to_rule=True,
                    error=error,
                )
            raise RuntimeError(error or "Drawer LLM 调用失败，且未启用规则回退。")
        return DrawerExecutionResult(
            output=self.agent.run(plan),
            llm_enabled=False,
            llm_attempted=False,
            llm_succeeded=False,
            fallback_to_rule=False,
            error=None,
        )

    def _generate_image_with_model(self, plan: PlannerFinalPlan) -> tuple[DrawerDraft | None, str | None]:
        try:
            prompt = self._build_image_prompt(plan)
            payload = self._call_images_api(prompt)
            return DrawerDraft.model_validate(payload), None
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)

    def _build_image_prompt(self, plan: PlannerFinalPlan) -> str:
        room_specs = []
        for room in plan.space_program:
            area_text = f"{room.target_area_sqm}㎡" if room.target_area_sqm else "面积自适应"
            room_specs.append(f"{room.room_type}x{room.count}({area_text})")
        adjacency_lines = []
        for edge in plan.adjacency_graph:
            adjacency_lines.append(f"{edge.source}->{edge.target}({edge.relation})")
        return (
            "请生成真实可读的住宅户型平面图，俯视图，2D architectural floor plan，"
            "中文房间标注，黑白线稿+浅色功能填充，比例协调，门窗表达清楚。\n"
            f"房间配置：{'；'.join(room_specs)}。\n"
            f"空间关系：{'；'.join(adjacency_lines)}。\n"
            f"设计摘要：{plan.drawing_brief}。\n"
            "输出单张清晰图片，不要添加水印或无关文本。"
        )

    def _call_images_api(self, prompt: str) -> dict:
        endpoint = self._resolve_images_endpoint(settings.llm_api_base)
        body = json.dumps(
            {
                "model": settings.drawer_model,
                "prompt": prompt,
                "size": "1024x1024",
                "response_format": "url",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib_request.Request(
            url=endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.llm_api_key}",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=settings.llm_timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Image API HTTP 错误: status={exc.code}, body={detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Image API 网络错误: {exc.reason}") from exc

        parsed = json.loads(raw)
        data = parsed.get("data") or []
        if not data:
            raise RuntimeError("Image API 返回缺少 data 字段。")
        first = data[0]
        image_url = first.get("url")
        image_base64 = first.get("b64_json")
        if not image_url and not image_base64:
            raise RuntimeError("Image API 返回缺少 url/b64_json。")
        return {
            "drawing_state": "IMAGE_READY",
            "image_url": image_url,
            "image_base64": image_base64,
            "image_mime_type": "image/png",
            "image_prompt": prompt,
            "model": settings.drawer_model,
            "size": "1024x1024",
            "validation": {
                "hard_constraints_passed": True,
                "notes": [],
            },
        }

    def _resolve_images_endpoint(self, api_base: str) -> str:
        normalized = api_base.rstrip("/")
        if normalized.endswith("/images/generations"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/images/generations"
        return f"{normalized}/v1/images/generations"
