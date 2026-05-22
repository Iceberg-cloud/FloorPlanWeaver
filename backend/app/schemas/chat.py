from pydantic import BaseModel, Field

from app.schemas.drawer import DrawerDraft
from app.schemas.layout import LayoutOutput
from app.schemas.planner import PlannerOutput


class CreateSessionResponse(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    session_id: str
    user_message: str
    draw_method: str = "auto"  # vector | multimodal | both | auto


class RegeneratePlanRequest(BaseModel):
    session_id: str
    modification_request: str
    draw_method: str = "auto"


class RegenerateDraftRequest(BaseModel):
    session_id: str
    draw_method: str = "auto"


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
    layout: AgentRuntimeStatus | None = None


class ChatResponse(BaseModel):
    status: str
    planner: PlannerOutput
    drawer: DrawerDraft | None = None
    layout: LayoutOutput | None = None
    progress: ProgressSnapshot
    runtime: RuntimeStatus


class ShutdownRequest(BaseModel):
    session_id: str | None = None


class ShutdownResponse(BaseModel):
    status: str
    message: str = ""
    session_cleared: bool = False
