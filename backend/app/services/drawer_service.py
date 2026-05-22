import base64
import json
from dataclasses import dataclass
from urllib import error, request as urllib_request

from app.agents.drawer_agent import DrawerAgent
from app.agents.prompts import build_drawer_image_prompt
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
        return build_drawer_image_prompt(plan)

    def _call_images_api(self, prompt: str) -> dict:
        endpoint = self._resolve_images_endpoint(settings.llm_api_base)
        body = json.dumps(
            {
                "model": settings.drawer_model,
                "prompt": prompt,
                "size": "1024x1024",
                "response_format": "b64_json",
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
            from app.services.llm_client import clamp_llm_timeout

            with urllib_request.urlopen(
                req, timeout=clamp_llm_timeout(settings.llm_timeout_seconds),
            ) as resp:
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
        image_base64 = first.get("b64_json") or first.get("image_base64")
        if not image_url and not image_base64:
            raise RuntimeError("Image API 返回缺少 url/b64_json。")
        payload = {
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
        return self._embed_image_for_ui(payload)

    def _embed_image_for_ui(self, payload: dict) -> dict:
        """Fetch remote URL into base64 so the browser can display without hotlink/CORS blocks."""
        if payload.get("image_base64"):
            return payload
        url = payload.get("image_url")
        if not url or not str(url).startswith(("http://", "https://")):
            return payload
        try:
            from app.services.llm_client import clamp_llm_timeout

            req = urllib_request.Request(str(url), method="GET")
            with urllib_request.urlopen(req, timeout=clamp_llm_timeout(60)) as resp:
                raw = resp.read()
            ctype = resp.headers.get_content_type() if hasattr(resp.headers, "get_content_type") else "image/png"
            payload["image_base64"] = base64.b64encode(raw).decode("ascii")
            payload["image_mime_type"] = ctype or "image/png"
        except Exception:
            pass
        return payload

    def _resolve_images_endpoint(self, api_base: str) -> str:
        normalized = api_base.rstrip("/")
        if normalized.endswith("/images/generations"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/images/generations"
        return f"{normalized}/v1/images/generations"
