from __future__ import annotations

from app.repositories.session_repo import InMemorySessionRepository
from app.schemas.chat import AgentRuntimeStatus, ChatResponse, ProgressSnapshot, RuntimeStatus
from app.schemas.layout import LayoutOutput, SiteOutline
from app.schemas.planner import PlannerAskForMore, PlannerFinalPlan
from app.schemas.session import ChatMessage
from app.services.drawer_service import DrawerService
from app.services.layout_service import LayoutService
from app.services.planner_service import PlannerService
from app.services.requirement_memory import (
    align_memory_with_outline,
    apply_delta_to_memory,
    build_regenerate_user_message,
    build_requirement_progress,
    effective_outline_area_sqm,
    merge_snapshot,
    outline_reminder_notices,
    reconcile_final_plan,
    snapshot_from_final_plan,
)
from app.services.planner_service import ensure_planner_ask
from app.core.config import settings


class Orchestrator:
    def __init__(
        self,
        repo: InMemorySessionRepository,
        planner_service: PlannerService,
        drawer_service: DrawerService,
        layout_service: LayoutService | None = None,
    ) -> None:
        self.repo = repo
        self.planner_service = planner_service
        self.drawer_service = drawer_service
        self.layout_service = layout_service

    @staticmethod
    def _has_site_outline(session) -> bool:
        o = session.site_outline
        return o is not None and len(o.vertices) >= 3

    @staticmethod
    def _build_notices(session, extra: list[str] | None = None) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in outline_reminder_notices(Orchestrator._has_site_outline(session)) + (extra or []):
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    def handle_chat(
        self,
        session_id: str,
        user_message: str,
        draw_method: str = "auto",
    ) -> ChatResponse:
        session = self.repo.get(session_id)
        if draw_method and draw_method != "auto":
            session.draw_method = draw_method
        session.messages.append(ChatMessage(role="user", content=user_message))

        prior_messages = session.messages[:-1]
        working_memory = apply_delta_to_memory(
            session.collected_requirements, user_message,
            chat_history=prior_messages,
        )
        working_memory, area_notices = align_memory_with_outline(
            working_memory, session.site_outline,
        )
        response_notices = self._build_notices(session, area_notices)

        force_plan = session.planner_ask_count >= settings.planner_max_ask_rounds
        planner_exec = self.planner_service.generate(
            user_message=user_message,
            collected_requirements=working_memory,
            chat_history=prior_messages,
            ask_count=session.planner_ask_count,
            force_finalize=force_plan,
        )
        planner_output = planner_exec.output

        if isinstance(planner_output, PlannerAskForMore):
            planner_output = ensure_planner_ask(
                planner_output,
                working_memory,
                user_message=user_message,
                ask_count=session.planner_ask_count,
            )
            if isinstance(planner_output, PlannerAskForMore):
                session.planner_ask_count += 1
                session.planner_state = "collecting"
                merged_collected = merge_snapshot(
                    session.collected_requirements,
                    planner_output.collected_snapshot,
                )
                merged_collected, _ = align_memory_with_outline(
                    merged_collected, session.site_outline,
                )
                session.collected_requirements = merged_collected
                session.messages.append(
                    ChatMessage(
                        role="assistant",
                        content="\n".join(planner_output.follow_up_questions),
                    )
                )
                self.repo.save(session)
                return ChatResponse(
                    status="collecting",
                    planner=planner_output,
                    progress=build_requirement_progress(merged_collected),
                    runtime=RuntimeStatus(
                        planner=AgentRuntimeStatus(
                            llm_enabled=planner_exec.llm_enabled,
                            llm_attempted=planner_exec.llm_attempted,
                            llm_succeeded=planner_exec.llm_succeeded,
                            fallback_to_rule=planner_exec.fallback_to_rule,
                            error=planner_exec.error,
                        ),
                        drawer=None,
                        layout=None,
                    ),
                    notices=response_notices,
                    has_site_outline=self._has_site_outline(session),
                )

        assert isinstance(planner_output, PlannerFinalPlan)
        planner_output = reconcile_final_plan(
            planner_output,
            merge_snapshot(session.collected_requirements, working_memory),
            outline=session.site_outline,
        )
        method = session.draw_method

        # --- Method A: Layout (vector) ---
        layout_exec_result = None
        if method in ("vector", "both"):
            layout_exec_result = self._generate_layout(session, planner_output)

        # --- Method B: Drawer (multimodal LLM) ---
        drawer_exec, drawer_error = None, None
        if method in ("multimodal", "both"):
            result = self._generate_drawer(planner_output)
            if result is not None:
                drawer_exec, drawer_error = result

        has_layout = layout_exec_result is not None
        has_drawer = drawer_exec is not None

        if not has_layout and not has_drawer:
            session.planner_state = "completed"
            session.latest_plan = planner_output
            session.collected_requirements = snapshot_from_final_plan(planner_output)
            session.revision_index += 1
            self.repo.save(session)
            error_msg = drawer_error or "生成失败"
            return ChatResponse(
                status="draft_failed",
                planner=planner_output,
                drawer=None,
                layout=None,
                progress=ProgressSnapshot(
                    collected_fields=sorted(list(session.collected_requirements.keys())),
                    missing_fields=[],
                ),
                runtime=RuntimeStatus(
                    planner=AgentRuntimeStatus(
                        llm_enabled=planner_exec.llm_enabled,
                        llm_attempted=planner_exec.llm_attempted,
                        llm_succeeded=planner_exec.llm_succeeded,
                        fallback_to_rule=planner_exec.fallback_to_rule,
                        error=planner_exec.error,
                    ),
                    drawer=AgentRuntimeStatus(
                        llm_enabled=True, llm_attempted=True,
                        llm_succeeded=False, fallback_to_rule=False,
                        error=error_msg,
                    ) if method in ("multimodal", "both") else None,
                    layout=layout_exec_result._as_runtime() if layout_exec_result else None,
                ),
                notices=response_notices,
                has_site_outline=self._has_site_outline(session),
            )

        session.planner_state = "completed"
        session.latest_plan = planner_output
        if drawer_exec is not None:
            session.latest_draft = drawer_exec.output
        if layout_exec_result is not None:
            session.latest_layout = layout_exec_result.output
        session.revision_index += 1
        session.collected_requirements = snapshot_from_final_plan(planner_output)
        session.messages.append(ChatMessage(role="assistant", content=planner_output.drawing_brief))
        self.repo.save(session)

        layout_runtime = layout_exec_result._as_runtime() if layout_exec_result else None
        drawer_runtime = None
        if drawer_exec is not None:
            drawer_runtime = AgentRuntimeStatus(
                llm_enabled=drawer_exec.llm_enabled,
                llm_attempted=drawer_exec.llm_attempted,
                llm_succeeded=drawer_exec.llm_succeeded,
                fallback_to_rule=drawer_exec.fallback_to_rule,
                error=drawer_exec.error,
            )
        elif drawer_error:
            drawer_runtime = AgentRuntimeStatus(
                llm_enabled=True, llm_attempted=True, llm_succeeded=False,
                fallback_to_rule=False, error=drawer_error,
            )

        return ChatResponse(
            status="completed",
            planner=planner_output,
            drawer=drawer_exec.output if drawer_exec else None,
            layout=layout_exec_result.output if layout_exec_result else None,
            progress=ProgressSnapshot(
                collected_fields=sorted(list(session.collected_requirements.keys())),
                missing_fields=[],
            ),
            runtime=RuntimeStatus(
                planner=AgentRuntimeStatus(
                    llm_enabled=planner_exec.llm_enabled,
                    llm_attempted=planner_exec.llm_attempted,
                    llm_succeeded=planner_exec.llm_succeeded,
                    fallback_to_rule=planner_exec.fallback_to_rule,
                    error=planner_exec.error,
                ),
                drawer=drawer_runtime,
                layout=layout_runtime,
            ),
            notices=response_notices,
            has_site_outline=self._has_site_outline(session),
        )

    def _generate_layout(self, session, plan: PlannerFinalPlan):
        if self.layout_service is None:
            return None
        outline = session.site_outline
        if outline is None:
            outline = self._make_default_outline(plan)
        try:
            layout_output = self.layout_service.generate(plan, outline)
        except Exception:
            return None
        return _LayoutResult(output=layout_output)

    def _generate_drawer(self, plan: PlannerFinalPlan):
        if not settings.drawer_use_llm and not settings.drawer_fallback_to_rule:
            return None
        try:
            return self.drawer_service.generate(plan), None
        except RuntimeError as exc:
            return None, str(exc)

    def _make_default_outline(self, plan: PlannerFinalPlan) -> SiteOutline:
        from app.schemas.layout import Point2D
        area = plan.project_profile.target_area_sqm or 80
        ratio = 1.4
        w = (area * ratio) ** 0.5
        h = w / ratio
        return SiteOutline(
            vertices=[
                Point2D(x=0, y=0), Point2D(x=w, y=0),
                Point2D(x=w, y=h), Point2D(x=0, y=h),
            ],
            entrance_edge=[0, 1],
            total_area_sqm=area,
            bounding_box={"width": w, "height": h},
            unit="meter",
        )

    def regenerate_plan(
        self,
        session_id: str,
        modification_request: str,
        draw_method: str = "auto",
    ) -> ChatResponse:
        session = self.repo.get(session_id)
        merged_request = modification_request
        if session.latest_plan:
            merged_request = build_regenerate_user_message(
                session.latest_plan,
                modification_request,
                session.collected_requirements,
            )
        return self.handle_chat(
            session_id=session_id,
            user_message=merged_request,
            draw_method=draw_method,
        )

    def regenerate_draft(self, session_id: str, draw_method: str = "auto") -> ChatResponse:
        session = self.repo.get(session_id)
        if session.latest_plan is None:
            raise ValueError("当前会话还没有可用于重绘的最终方案。")

        method = draw_method if draw_method != "auto" else session.draw_method

        layout_exec_result = None
        if method in ("vector", "both"):
            layout_exec_result = self._generate_layout(session, session.latest_plan)

        drawer_exec, drawer_error = None, None
        if method in ("multimodal", "both"):
            result = self._generate_drawer(session.latest_plan)
            if result is not None:
                drawer_exec, drawer_error = result

        if drawer_exec is None and layout_exec_result is None:
            return ChatResponse(
                status="draft_failed",
                planner=session.latest_plan,
                drawer=None,
                layout=None,
                progress=ProgressSnapshot(
                    collected_fields=sorted(list(session.collected_requirements.keys())),
                    missing_fields=[],
                ),
                runtime=RuntimeStatus(
                    planner=AgentRuntimeStatus(llm_enabled=False, llm_attempted=False,
                                               llm_succeeded=False, fallback_to_rule=False),
                    drawer=AgentRuntimeStatus(llm_enabled=True, llm_attempted=True,
                                              llm_succeeded=False, fallback_to_rule=False,
                                              error=drawer_error),
                    layout=None,
                ),
            )

        if drawer_exec:
            session.latest_draft = drawer_exec.output
        if layout_exec_result:
            session.latest_layout = layout_exec_result.output
        session.revision_index += 1
        self.repo.save(session)
        return ChatResponse(
            status="completed",
            planner=session.latest_plan,
            drawer=drawer_exec.output if drawer_exec else session.latest_draft,
            layout=layout_exec_result.output if layout_exec_result else session.latest_layout,
            progress=ProgressSnapshot(
                collected_fields=sorted(list(session.collected_requirements.keys())),
                missing_fields=[],
            ),
            runtime=RuntimeStatus(
                planner=AgentRuntimeStatus(llm_enabled=False, llm_attempted=False,
                                           llm_succeeded=False, fallback_to_rule=False),
                drawer=AgentRuntimeStatus(
                    llm_enabled=drawer_exec.llm_enabled if drawer_exec else False,
                    llm_attempted=drawer_exec.llm_attempted if drawer_exec else True,
                    llm_succeeded=drawer_exec.llm_succeeded if drawer_exec else False,
                    fallback_to_rule=drawer_exec.fallback_to_rule if drawer_exec else False,
                    error=drawer_exec.error if drawer_exec else drawer_error,
                ) if method in ("multimodal", "both") else None,
                layout=layout_exec_result._as_runtime() if layout_exec_result else None,
            ),
        )


class _LayoutResult:
    def __init__(self, output: LayoutOutput):
        self.output = output

    def _as_runtime(self) -> AgentRuntimeStatus:
        return AgentRuntimeStatus(
            llm_enabled=False,
            llm_attempted=False,
            llm_succeeded=False,
            fallback_to_rule=True,
            error=None,
        )
