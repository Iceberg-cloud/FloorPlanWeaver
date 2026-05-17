from app.repositories.session_repo import InMemorySessionRepository
from app.schemas.chat import AgentRuntimeStatus, ChatResponse, ProgressSnapshot, RuntimeStatus
from app.schemas.planner import PlannerAskForMore, PlannerFinalPlan
from app.schemas.session import ChatMessage
from app.services.drawer_service import DrawerService
from app.services.planner_service import PlannerService


class Orchestrator:
    def __init__(
        self,
        repo: InMemorySessionRepository,
        planner_service: PlannerService,
        drawer_service: DrawerService,
    ) -> None:
        self.repo = repo
        self.planner_service = planner_service
        self.drawer_service = drawer_service

    def handle_chat(self, session_id: str, user_message: str) -> ChatResponse:
        session = self.repo.get(session_id)
        session.messages.append(ChatMessage(role="user", content=user_message))

        planner_exec = self.planner_service.generate(
            user_message=user_message,
            collected_requirements=session.collected_requirements,
        )
        planner_output = planner_exec.output

        if isinstance(planner_output, PlannerAskForMore):
            session.planner_state = "collecting"
            session.collected_requirements = planner_output.collected_snapshot
            session.messages.append(
                ChatMessage(role="assistant", content="\n".join(planner_output.follow_up_questions))
            )
            self.repo.save(session)
            return ChatResponse(
                status="collecting",
                planner=planner_output,
                progress=ProgressSnapshot(
                    collected_fields=sorted(list(session.collected_requirements.keys())),
                    missing_fields=planner_output.missing_fields,
                ),
                runtime=RuntimeStatus(
                    planner=AgentRuntimeStatus(
                        llm_enabled=planner_exec.llm_enabled,
                        llm_attempted=planner_exec.llm_attempted,
                        llm_succeeded=planner_exec.llm_succeeded,
                        fallback_to_rule=planner_exec.fallback_to_rule,
                        error=planner_exec.error,
                    ),
                    drawer=None,
                ),
            )

        assert isinstance(planner_output, PlannerFinalPlan)
        try:
            drawer_exec = self.drawer_service.generate(planner_output)
        except RuntimeError as exc:
            session.planner_state = "completed"
            session.latest_plan = planner_output
            session.revision_index += 1
            self.repo.save(session)
            return ChatResponse(
                status="draft_failed",
                planner=planner_output,
                drawer=None,
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
                        llm_enabled=True,
                        llm_attempted=True,
                        llm_succeeded=False,
                        fallback_to_rule=False,
                        error=str(exc),
                    ),
                ),
            )
        draft = drawer_exec.output
        session.planner_state = "completed"
        session.latest_plan = planner_output
        session.latest_draft = draft
        session.revision_index += 1
        session.collected_requirements = {
            "building_type": planner_output.project_profile.building_type,
            "target_area_sqm": planner_output.project_profile.target_area_sqm,
            "layout_type": planner_output.project_profile.layout_type,
            "orientation": planner_output.project_profile.orientation,
            "room_program": [item.model_dump() for item in planner_output.space_program],
            "adjacency_rules": [item.model_dump() for item in planner_output.adjacency_graph],
        }
        session.messages.append(ChatMessage(role="assistant", content=planner_output.drawing_brief))
        self.repo.save(session)
        return ChatResponse(
            status="completed",
            planner=planner_output,
            drawer=draft,
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
                    llm_enabled=drawer_exec.llm_enabled,
                    llm_attempted=drawer_exec.llm_attempted,
                    llm_succeeded=drawer_exec.llm_succeeded,
                    fallback_to_rule=drawer_exec.fallback_to_rule,
                    error=drawer_exec.error,
                ),
            ),
        )

    def regenerate_plan(self, session_id: str, modification_request: str) -> ChatResponse:
        session = self.repo.get(session_id)
        merged_request = modification_request
        if session.latest_plan:
            merged_request = (
                f"基于既有方案进行修改。已有绘图摘要：{session.latest_plan.drawing_brief}。修改意见：{modification_request}"
            )
        return self.handle_chat(session_id=session_id, user_message=merged_request)

    def regenerate_draft(self, session_id: str) -> ChatResponse:
        session = self.repo.get(session_id)
        if session.latest_plan is None:
            raise ValueError("当前会话还没有可用于重绘的最终方案。")
        try:
            drawer_exec = self.drawer_service.generate(session.latest_plan)
        except RuntimeError as exc:
            return ChatResponse(
                status="draft_failed",
                planner=session.latest_plan,
                drawer=None,
                progress=ProgressSnapshot(
                    collected_fields=sorted(list(session.collected_requirements.keys())),
                    missing_fields=[],
                ),
                runtime=RuntimeStatus(
                    planner=AgentRuntimeStatus(
                        llm_enabled=False,
                        llm_attempted=False,
                        llm_succeeded=False,
                        fallback_to_rule=False,
                        error=None,
                    ),
                    drawer=AgentRuntimeStatus(
                        llm_enabled=True,
                        llm_attempted=True,
                        llm_succeeded=False,
                        fallback_to_rule=False,
                        error=str(exc),
                    ),
                ),
            )
        draft = drawer_exec.output
        session.latest_draft = draft
        session.revision_index += 1
        self.repo.save(session)
        return ChatResponse(
            status="completed",
            planner=session.latest_plan,
            drawer=draft,
            progress=ProgressSnapshot(
                collected_fields=sorted(list(session.collected_requirements.keys())),
                missing_fields=[],
            ),
            runtime=RuntimeStatus(
                planner=AgentRuntimeStatus(
                    llm_enabled=False,
                    llm_attempted=False,
                    llm_succeeded=False,
                    fallback_to_rule=False,
                    error=None,
                ),
                drawer=AgentRuntimeStatus(
                    llm_enabled=drawer_exec.llm_enabled,
                    llm_attempted=drawer_exec.llm_attempted,
                    llm_succeeded=drawer_exec.llm_succeeded,
                    fallback_to_rule=drawer_exec.fallback_to_rule,
                    error=drawer_exec.error,
                ),
            ),
        )
