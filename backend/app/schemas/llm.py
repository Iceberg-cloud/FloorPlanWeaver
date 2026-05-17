from typing import Any

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMJsonRequest(BaseModel):
    system_prompt: str
    messages: list[LLMMessage]
    model: str
    json_schema: dict[str, Any] | None = None
    timeout_seconds: int = 45
    max_retries: int = 2
    temperature: float = 0.2
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMJsonResponse(BaseModel):
    raw_text: str
    data: dict[str, Any]
    provider: str
    model: str
