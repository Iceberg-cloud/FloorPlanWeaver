import json
import re
import socket
import time
from typing import Any, Protocol
from urllib import error, request as urllib_request

from app.core.config import settings
from app.schemas.llm import LLMJsonRequest, LLMJsonResponse


def clamp_llm_timeout(seconds: int | float | None) -> int:
    """Cap per-request HTTP wait; Windows urllib only accepts a single timeout value."""
    cap = max(10, settings.llm_hard_timeout_seconds)
    try:
        value = int(seconds or cap)
    except (TypeError, ValueError):
        value = cap
    return max(10, min(value, cap))


class ProviderAdapter(Protocol):
    def generate(self, request: LLMJsonRequest) -> LLMJsonResponse:
        ...


class MockProviderAdapter:
    """
    本地占位 Provider，用于接口联调。
    """

    def generate(self, request: LLMJsonRequest) -> LLMJsonResponse:
        fake = {
            "agent_state": "ASK_FOR_MORE",
            "missing_fields": ["target_area_sqm"],
            "follow_up_questions": ["请补充目标面积（例如 120㎡）。"],
            "collected_snapshot": {},
        }
        return LLMJsonResponse(
            raw_text=json.dumps(fake, ensure_ascii=False),
            data=fake,
            provider="mock",
            model=request.model,
        )


class HttpCompatibleProviderAdapter:
    """
    兼容 OpenAI 风格 Chat Completions 的预留适配器。
    这里仅定义稳定接口，便于后续直接接入真实 API。
    """

    def __init__(self, *, api_base: str, api_key: str, provider: str) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.provider = provider

    def generate(self, request: LLMJsonRequest) -> LLMJsonResponse:
        raw_text = self._call_provider_api(request)
        data = self._extract_json(raw_text)
        return LLMJsonResponse(
            raw_text=raw_text,
            data=data,
            provider=self.provider,
            model=request.model,
        )

    def _call_provider_api(self, request: LLMJsonRequest) -> str:
        if not self.api_base:
            raise ValueError("LLM_API_BASE 未配置。")
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置。")

        endpoint = (
            self.api_base
            if self.api_base.endswith("/chat/completions")
            else f"{self.api_base}/chat/completions"
        )
        payload = self._build_payload(request)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = urllib_request.Request(
            url=endpoint,
            data=body,
            headers=headers,
            method="POST",
        )

        http_timeout = clamp_llm_timeout(request.timeout_seconds)
        try:
            with urllib_request.urlopen(req, timeout=http_timeout) as resp:
                response_raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"LLM HTTP 错误: status={exc.code}, body={error_body}"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise TimeoutError(
                f"LLM 请求超时（上限 {http_timeout}s，硬限制 {settings.llm_hard_timeout_seconds}s）。"
                "可改用更快模型或检查网络。"
            ) from exc
        except error.URLError as exc:
            reason = str(exc.reason)
            if "timed out" in reason.lower() or "timeout" in reason.lower():
                raise TimeoutError(
                    f"LLM 请求超时（上限 {http_timeout}s）。请检查网络或代理。"
                ) from exc
            raise RuntimeError(f"LLM 网络错误: {exc.reason}") from exc

        response_data = json.loads(response_raw)
        return self._extract_content_from_response(response_data)

    def _build_payload(self, req: LLMJsonRequest) -> dict[str, Any]:
        messages = [{"role": "system", "content": req.system_prompt}]
        messages.extend([msg.model_dump() for msg in req.messages])

        payload: dict[str, Any] = {
            "model": req.model,
            "messages": messages,
            "temperature": req.temperature,
        }
        if req.metadata:
            payload["metadata"] = req.metadata

        if req.json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": req.json_schema,
                    "strict": True,
                },
            }
        else:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _extract_content_from_response(self, data: dict[str, Any]) -> str:
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("LLM 响应缺少 choices 字段。")

        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
            if text_parts:
                return "".join(text_parts)
        raise ValueError("LLM 响应缺少可解析 content。")

    def _extract_json(self, raw_text: str) -> dict[str, Any]:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            match = re.search(r"```json\s*(\{.*\})\s*```", raw_text, flags=re.S)
            if match:
                return json.loads(match.group(1))
            match = re.search(r"(\{.*\})", raw_text, flags=re.S)
            if match:
                return json.loads(match.group(1))
            raise ValueError("模型返回内容不是合法 JSON。") from exc


class LLMClient:
    def __init__(self) -> None:
        self.adapter = self._build_adapter()

    def _build_adapter(self) -> ProviderAdapter:
        if settings.llm_mock_mode or settings.llm_provider == "mock":
            return MockProviderAdapter()
        return HttpCompatibleProviderAdapter(
            api_base=settings.llm_api_base,
            api_key=settings.llm_api_key,
            provider=settings.llm_provider,
        )

    def generate_json(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, str]],
        model: str,
        json_schema: dict[str, Any] | None = None,
        timeout_seconds: int = 120,
        max_retries: int = 2,
        temperature: float = 0.2,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        hard_cap = settings.llm_hard_timeout_seconds
        per_call_timeout = clamp_llm_timeout(timeout_seconds)
        deadline = time.time() + hard_cap

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            remaining = deadline - time.time()
            if remaining < 2:
                raise TimeoutError(
                    f"LLM 总耗时已超过硬限制 {hard_cap}s（含重试）。"
                )

            attempt_timeout = clamp_llm_timeout(min(per_call_timeout, int(remaining)))
            req = LLMJsonRequest(
                system_prompt=system_prompt,
                messages=messages,
                model=model,
                json_schema=json_schema,
                timeout_seconds=attempt_timeout,
                max_retries=max_retries,
                temperature=temperature,
                metadata=metadata or {},
            )
            try:
                response = self.adapter.generate(req)
                return response.data
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == max_retries:
                    break
                time.sleep(min(0.4 * (attempt + 1), max(0.0, deadline - time.time() - 1)))

        assert last_error is not None
        raise RuntimeError(f"LLM 调用失败: {last_error}") from last_error
