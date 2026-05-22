import json
from dataclasses import dataclass

from pydantic import ValidationError

from app.agents.prompts import PLANNER_SYSTEM_PROMPT
from app.agents.planner_agent import PlannerAgent
from app.schemas.planner import PlannerAskForMore, PlannerFinalPlan
from app.services.llm_client import LLMClient
from app.services.requirement_memory import (
    apply_delta_to_memory,
    build_planner_messages,
    compute_missing_fields,
    filter_missing_fields,
    merge_snapshot,
)
from app.core.config import settings
from app.schemas.session import ChatMessage


def _normalize_agent_state(raw: object) -> str:
    text = str(raw or "").strip().upper().replace(" ", "_").replace("-", "_")
    if "FINAL" in text and "PLAN" in text:
        return "FINAL_PLAN"
    if "ASK" in text:
        return "ASK_FOR_MORE"
    return text


def _unwrap_planner_payload(raw: object) -> dict:
    """Accept flat or nested LLM JSON shapes."""
    if not isinstance(raw, dict):
        return {}
    if raw.get("agent_state") is not None:
        return dict(raw)
    for key in ("planner", "data", "result", "output"):
        nested = raw.get(key)
        if isinstance(nested, dict) and nested.get("agent_state") is not None:
            merged = dict(raw)
            merged.update(nested)
            return merged
    return dict(raw)


@dataclass
class PlannerExecutionResult:
    output: PlannerAskForMore | PlannerFinalPlan
    llm_enabled: bool
    llm_attempted: bool
    llm_succeeded: bool
    fallback_to_rule: bool
    error: str | None = None


def _has_final_plan_fields(payload: dict) -> bool:
    if not payload.get("drawing_brief"):
        return False
    if not isinstance(payload.get("design_goals"), list) or not payload["design_goals"]:
        return False
    if not isinstance(payload.get("space_program"), list) or not payload["space_program"]:
        return False
    if not isinstance(payload.get("adjacency_graph"), list):
        return False
    profile = payload.get("project_profile")
    return isinstance(profile, dict) and bool(profile)


def _merge_final_plan_dict(rule: dict, llm: dict) -> dict:
    """Rule baseline with non-empty LLM fields overriding."""
    out = dict(rule)
    for key, val in llm.items():
        if key == "agent_state" or val is None:
            continue
        if key == "project_profile" and isinstance(val, dict):
            base = out.get("project_profile") or {}
            if isinstance(base, dict):
                out["project_profile"] = {**base, **{k: v for k, v in val.items() if v is not None and v != ""}}
            else:
                out["project_profile"] = val
        elif key in ("space_program", "adjacency_graph", "design_goals", "change_summary", "lifestyle_tags"):
            if isinstance(val, list) and val:
                out[key] = val
        elif key in ("circulation", "openings_strategy", "orientation_daylighting", "zoning", "household_profile", "owner_summary"):
            if isinstance(val, dict) and val:
                base = out.get(key) or {}
                out[key] = {**base, **val} if isinstance(base, dict) else val
        elif key == "drawing_brief" and val:
            out["drawing_brief"] = val
    out["agent_state"] = "FINAL_PLAN"
    return out


def _should_force_final_plan(ask_count: int) -> bool:
    return ask_count >= settings.planner_max_ask_rounds


def _snapshot_complete(snapshot: dict) -> bool:
    return len(compute_missing_fields(snapshot)) == 0


def _rule_finalize(
    user_message: str,
    memory: dict,
    *,
    ask_count: int = 0,
) -> PlannerFinalPlan:
    out = PlannerAgent().run(
        user_message=user_message,
        collected=dict(memory),
        force_finalize=True,
        ask_count=ask_count,
    )
    if isinstance(out, PlannerAskForMore):
        out = PlannerAgent().run(
            user_message=user_message,
            collected=dict(memory),
            force_finalize=True,
            ask_count=max(ask_count, settings.planner_max_ask_rounds),
        )
    assert isinstance(out, PlannerFinalPlan)
    return out


def _user_message_implies_complete(text: str) -> bool:
    """Heuristic: rich first message should not trigger ASK (P1)."""
    probe = apply_delta_to_memory({}, text)
    if _snapshot_complete(probe):
        return True
    has_area = bool(probe.get("target_area_sqm"))
    has_layout = bool(probe.get("layout_type"))
    rooms = probe.get("room_program") or []
    return has_area and has_layout and len(rooms) >= 3


def _coerce_planner_payload(
    payload: dict,
    collected_requirements: dict,
    user_message: str,
    *,
    ask_count: int = 0,
) -> dict:
    """Fill required planner fields when the LLM returns a partial object."""
    payload = _unwrap_planner_payload(payload)
    state = _normalize_agent_state(payload.get("agent_state"))
    if state not in ("ASK_FOR_MORE", "FINAL_PLAN"):
        state = "ASK_FOR_MORE"
    payload["agent_state"] = state
    agent = PlannerAgent()

    if _should_force_final_plan(ask_count):
        merged = dict(collected_requirements)
        merged.update(payload.get("collected_snapshot") or {})
        return agent.run(
            user_message=user_message,
            collected=merged,
            force_finalize=True,
            ask_count=ask_count,
        ).model_dump()

    if state == "FINAL_PLAN":
        if _has_final_plan_fields(payload):
            return payload

        merged_collected = dict(collected_requirements)
        merged_collected.update(payload.get("collected_snapshot") or {})
        rule_out = agent.run(
            user_message=user_message,
            collected=merged_collected,
            ask_count=ask_count,
            force_finalize=_should_force_final_plan(ask_count),
        )
        if rule_out.agent_state == "ASK_FOR_MORE":
            return rule_out.model_dump()

        rule_dict = rule_out.model_dump()
        return _merge_final_plan_dict(rule_dict, payload)

    snapshot = dict(collected_requirements)
    snapshot.update(payload.get("collected_snapshot") or {})

    if _snapshot_complete(snapshot) or _user_message_implies_complete(user_message):
        return _rule_finalize(
            user_message, snapshot, ask_count=ask_count,
        ).model_dump()

    missing = payload.get("missing_fields")
    if not isinstance(missing, list) or not missing:
        missing = compute_missing_fields(snapshot)
    else:
        missing = filter_missing_fields(list(missing), snapshot)
    if not missing:
        return _rule_finalize(
            user_message, snapshot, ask_count=ask_count,
        ).model_dump()

    questions = payload.get("follow_up_questions")
    if not isinstance(questions, list) or not questions:
        questions = agent._build_questions(missing, snapshot)
    questions = list(questions)[:2]
    if not questions:
        questions = ["请补充户型类型、建筑面积与房间需求（例如：三居、约120㎡）。"]

    return {
        "agent_state": "ASK_FOR_MORE",
        "missing_fields": missing[:2] if missing else compute_missing_fields(snapshot)[:2],
        "follow_up_questions": questions,
        "collected_snapshot": snapshot,
    }


def ensure_planner_ask(
    ask: PlannerAskForMore,
    memory: dict,
    *,
    user_message: str = "",
    ask_count: int = 0,
) -> PlannerAskForMore | PlannerFinalPlan:
    """Align ask payload with working memory; finalize when nothing is missing."""
    snapshot = merge_snapshot(memory, ask.collected_snapshot)
    missing = compute_missing_fields(snapshot)
    if ask.missing_fields:
        filtered = filter_missing_fields(list(ask.missing_fields), snapshot)
        if filtered:
            missing = filtered

    if not missing or (user_message and _user_message_implies_complete(user_message)):
        return _rule_finalize(user_message or "", snapshot, ask_count=ask_count)

    questions = list(ask.follow_up_questions or [])
    if not questions:
        questions = PlannerAgent()._build_questions(missing[:2], snapshot)
    if not questions:
        questions = ["请补充户型类型、建筑面积与房间需求（例如：三居、约120㎡）。"]
    return PlannerAskForMore(
        agent_state="ASK_FOR_MORE",
        missing_fields=missing[:2],
        follow_up_questions=questions[:2],
        collected_snapshot=snapshot,
    )


def _build_ask_for_more(coerced: dict) -> PlannerAskForMore:
    """Construct without model_validate so partial LLM JSON never triggers required-field errors."""
    return PlannerAskForMore(
        agent_state="ASK_FOR_MORE",
        missing_fields=list(coerced.get("missing_fields") or []),
        follow_up_questions=list(coerced.get("follow_up_questions") or []),
        collected_snapshot=dict(coerced.get("collected_snapshot") or {}),
    )


def _parse_planner_llm_payload(
    payload: dict,
    collected_requirements: dict,
    user_message: str,
    *,
    ask_count: int = 0,
) -> PlannerAskForMore | PlannerFinalPlan:
    """Coerce then validate; fall back to rule planner on any validation error."""
    coerced = _coerce_planner_payload(
        payload, collected_requirements, user_message, ask_count=ask_count,
    )
    try:
        if coerced.get("agent_state") == "FINAL_PLAN":
            return PlannerFinalPlan.model_validate(coerced)
        ask = _build_ask_for_more(coerced)
        resolved = ensure_planner_ask(
            ask, collected_requirements, user_message=user_message, ask_count=ask_count,
        )
        if isinstance(resolved, PlannerFinalPlan):
            return resolved
        return resolved
    except ValidationError:
        out = PlannerAgent().run(
            user_message=user_message,
            collected=dict(collected_requirements),
            ask_count=ask_count,
            force_finalize=_should_force_final_plan(ask_count),
        )
        if isinstance(out, PlannerAskForMore):
            resolved = ensure_planner_ask(
                out, collected_requirements, user_message=user_message, ask_count=ask_count,
            )
            if isinstance(resolved, PlannerFinalPlan):
                return resolved
            return resolved
        return out


def _ensure_final_output(
    output: PlannerAskForMore | PlannerFinalPlan,
    *,
    user_message: str,
    collected: dict,
    ask_count: int,
) -> PlannerFinalPlan | PlannerAskForMore:
    if isinstance(output, PlannerFinalPlan):
        return output
    if _should_force_final_plan(ask_count):
        return PlannerAgent().run(
            user_message=user_message,
            collected=collected,
            force_finalize=True,
            ask_count=ask_count,
        )
    if isinstance(output, PlannerAskForMore):
        snapshot = merge_snapshot(collected, output.collected_snapshot)
        if _snapshot_complete(snapshot) or _user_message_implies_complete(user_message):
            return _rule_finalize(user_message, snapshot, ask_count=ask_count)
        resolved = ensure_planner_ask(
            output, collected, user_message=user_message, ask_count=ask_count,
        )
        if isinstance(resolved, PlannerFinalPlan):
            return resolved
        return resolved
    return output


class PlannerService:
    def __init__(self) -> None:
        self.agent = PlannerAgent()
        self.llm = LLMClient()

    def generate(
        self,
        *,
        user_message: str,
        collected_requirements: dict,
        chat_history: list[ChatMessage] | None = None,
        ask_count: int = 0,
        force_finalize: bool = False,
    ) -> PlannerExecutionResult:
        working = merge_snapshot(collected_requirements, {})
        force = force_finalize or _should_force_final_plan(ask_count)
        if settings.planner_use_llm:
            llm_result, error = self._generate_with_llm(
                user_message, working, chat_history=chat_history, ask_count=ask_count,
            )
            if llm_result is not None:
                out = _ensure_final_output(
                    llm_result,
                    user_message=user_message,
                    collected=working,
                    ask_count=ask_count,
                )
                return PlannerExecutionResult(
                    output=out,
                    llm_enabled=True,
                    llm_attempted=True,
                    llm_succeeded=True,
                    fallback_to_rule=False,
                    error=None,
                )
            out = self.agent.run(
                user_message=user_message,
                collected=working,
                ask_count=ask_count,
                force_finalize=force,
            )
            if isinstance(out, PlannerAskForMore):
                resolved = ensure_planner_ask(
                    out, working, user_message=user_message, ask_count=ask_count,
                )
                out = resolved
            return PlannerExecutionResult(
                output=out,
                llm_enabled=True,
                llm_attempted=True,
                llm_succeeded=False,
                fallback_to_rule=True,
                error=error,
            )
        out = self.agent.run(
            user_message=user_message,
            collected=working,
            ask_count=ask_count,
            force_finalize=force,
        )
        if isinstance(out, PlannerAskForMore):
            resolved = ensure_planner_ask(
                out, working, user_message=user_message, ask_count=ask_count,
            )
            out = resolved
        return PlannerExecutionResult(
            output=out,
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
        *,
        chat_history: list[ChatMessage] | None = None,
        ask_count: int = 0,
    ) -> tuple[PlannerAskForMore | PlannerFinalPlan | None, str | None]:
        try:
            llm_messages = build_planner_messages(
                working_memory=collected_requirements,
                user_message=user_message,
                chat_history=chat_history,
                max_turns=settings.planner_max_history_turns,
            )
            payload = self.llm.generate_json(
                system_prompt=PLANNER_SYSTEM_PROMPT,
                messages=llm_messages,
                model=settings.planner_model,
                timeout_seconds=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
                metadata={"agent": "planner"},
            )
            if not isinstance(payload, dict):
                payload = {}
            return _parse_planner_llm_payload(
                payload, collected_requirements, user_message, ask_count=ask_count,
            ), None
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)
