import json
from dataclasses import dataclass

from app.agents.prompts import PLANNER_SYSTEM_PROMPT
from app.agents.planner_agent import PlannerAgent
from app.schemas.planner import PlannerAskForMore, PlannerFinalPlan
from app.services.llm_client import LLMClient
from app.core.config import settings


@dataclass
class PlannerExecutionResult:
    output: PlannerAskForMore | PlannerFinalPlan
    llm_enabled: bool
    llm_attempted: bool
    llm_succeeded: bool
    fallback_to_rule: bool
    error: str | None = None


class PlannerService:
    def __init__(self) -> None:
        self.agent = PlannerAgent()
        self.llm = LLMClient()

    def generate(
        self,
        *,
        user_message: str,
        collected_requirements: dict,
    ) -> PlannerExecutionResult:
        if settings.planner_use_llm:
            llm_result, error = self._generate_with_llm(user_message, collected_requirements)
            if llm_result is not None:
                return PlannerExecutionResult(
                    output=llm_result,
                    llm_enabled=True,
                    llm_attempted=True,
                    llm_succeeded=True,
                    fallback_to_rule=False,
                    error=None,
                )
            return PlannerExecutionResult(
                output=self.agent.run(user_message=user_message, collected=collected_requirements),
                llm_enabled=True,
                llm_attempted=True,
                llm_succeeded=False,
                fallback_to_rule=True,
                error=error,
            )
        return PlannerExecutionResult(
            output=self.agent.run(user_message=user_message, collected=collected_requirements),
            llm_enabled=False,
            llm_attempted=False,
            llm_succeeded=False,
            fallback_to_rule=False,
            error=None,
        )

    def _generate_with_llm(
        self,
        user_message: str,
        collected_requirements: dict,
    ) -> tuple[PlannerAskForMore | PlannerFinalPlan | None, str | None]:
        try:
            payload = self.llm.generate_json(
                system_prompt=PLANNER_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "已收集需求快照："
                            + json.dumps(collected_requirements, ensure_ascii=False)
                            + "\n本轮用户输入："
                            + user_message
                        ),
                    }
                ],
                model=settings.planner_model,
                json_schema={
                    "type": "object",
                    "properties": {
                        "agent_state": {"type": "string"},
                    },
                    "required": ["agent_state"],
                },
                timeout_seconds=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
                metadata={"agent": "planner"},
            )
            if payload.get("agent_state") == "FINAL_PLAN":
                return PlannerFinalPlan.model_validate(payload), None
            return PlannerAskForMore.model_validate(payload), None
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)
