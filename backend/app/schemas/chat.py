from pydantic import BaseModel, Field

from app.schemas.drawer import DrawerDraft
from app.schemas.planner import PlannerAskForMore, PlannerFinalPlan


class CreateSessionResponse(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    session_id: str
    user_message: str


class RegeneratePlanRequest(BaseModel):
    session_id: str
    modification_request: str


class RegenerateDraftRequest(BaseModel):
    session_id: str


class ProgressSnapshot(BaseModel):
    collected_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class AgentRuntimeStatus(BaseModel):
    llm_enabled: bool = False
    llm_attempted: bool = False
    llm_succeeded: bool = False
    fallback_to_rule: bool = False
    error: str | None = None


class RuntimeStatus(BaseModel):
    planner: AgentRuntimeStatus
    drawer: AgentRuntimeStatus | None = None


class ChatResponse(BaseModel):
    status: str
    planner: PlannerAskForMore | PlannerFinalPlan
    drawer: DrawerDraft | None = None
    progress: ProgressSnapshot
    runtime: RuntimeStatus
