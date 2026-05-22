from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class ProjectProfile(BaseModel):
    building_type: str = ""
    target_area_sqm: float | None = None
    layout_type: str = ""
    orientation: str = ""


class HouseholdProfile(BaseModel):
    total_people: int | None = None
    has_elderly: bool = False
    has_children: bool = False
    needs_study_room: bool = False
    description: str = ""


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


class RoomAreaRow(BaseModel):
    room_type: str
    count: int
    area_sqm: float
    ratio_percent: float


class AreaValidation(BaseModel):
    target_total_sqm: float | None = None
    planned_total_sqm: float = 0
    deviation_percent: float | None = None
    passed: bool = True
    message: str = ""


class OwnerSummary(BaseModel):
    headline: str = ""
    household_text: str = ""
    lifestyle_text: str = ""
    room_rows: list[RoomAreaRow] = Field(default_factory=list)
    circulation_text: str = ""
    zoning_text: str = ""
    adjacency_text: str = ""
    daylight_text: str = ""
    area_validation: AreaValidation = Field(default_factory=AreaValidation)


class PlannerAskForMore(BaseModel):
    agent_state: Literal["ASK_FOR_MORE"]
    missing_fields: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    collected_snapshot: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _fill_partial_llm_payload(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if data.get("agent_state") != "ASK_FOR_MORE":
            return data
        if data.get("missing_fields") is None or not isinstance(data.get("missing_fields"), list):
            data["missing_fields"] = []
        if data.get("follow_up_questions") is None or not isinstance(
            data.get("follow_up_questions"), list,
        ):
            data["follow_up_questions"] = []
        if data.get("collected_snapshot") is None or not isinstance(
            data.get("collected_snapshot"), dict,
        ):
            data["collected_snapshot"] = {}
        return data


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
    household_profile: HouseholdProfile = Field(default_factory=HouseholdProfile)
    lifestyle_tags: list[str] = Field(default_factory=list)
    owner_summary: OwnerSummary = Field(default_factory=OwnerSummary)


PlannerOutput = Annotated[
    Union[PlannerAskForMore, PlannerFinalPlan],
    Field(discriminator="agent_state"),
]
