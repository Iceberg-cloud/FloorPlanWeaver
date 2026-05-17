from typing import Literal

from pydantic import BaseModel, Field


class ProjectProfile(BaseModel):
    building_type: str = ""
    target_area_sqm: float | None = None
    layout_type: str = ""
    orientation: str = ""


class SpaceProgramItem(BaseModel):
    room_type: str
    count: int = 1
    target_area_sqm: float | None = None
    notes: str = ""


class AdjacencyRule(BaseModel):
    source: str
    target: str
    relation: Literal["required", "preferred"] = "preferred"
    description: str = ""


class PlannerAskForMore(BaseModel):
    agent_state: Literal["ASK_FOR_MORE"]
    missing_fields: list[str]
    follow_up_questions: list[str]
    collected_snapshot: dict = Field(default_factory=dict)


class PlannerFinalPlan(BaseModel):
    agent_state: Literal["FINAL_PLAN"]
    project_profile: ProjectProfile
    design_goals: list[str]
    space_program: list[SpaceProgramItem]
    adjacency_graph: list[AdjacencyRule]
    circulation: dict = Field(default_factory=dict)
    openings_strategy: dict = Field(default_factory=dict)
    orientation_daylighting: dict = Field(default_factory=dict)
    zoning: dict = Field(default_factory=dict)
    drawing_brief: str
    change_summary: list[str] = Field(default_factory=list)


PlannerOutput = PlannerAskForMore | PlannerFinalPlan
