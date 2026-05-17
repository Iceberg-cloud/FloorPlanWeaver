from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.drawer import DrawerDraft
from app.schemas.planner import PlannerFinalPlan


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SessionState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    messages: list[ChatMessage] = Field(default_factory=list)
    collected_requirements: dict = Field(default_factory=dict)
    planner_state: Literal["collecting", "completed"] = "collecting"
    latest_plan: PlannerFinalPlan | None = None
    latest_draft: DrawerDraft | None = None
    revision_index: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)
