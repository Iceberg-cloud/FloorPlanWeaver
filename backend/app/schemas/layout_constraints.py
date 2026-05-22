"""Structured layout constraints (LLM parses intent; geometry from grid search)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoomPlacementConstraint(BaseModel):
    """Normalized constraint from LLM semantic — no final geometry coordinates."""

    name: str
    room_type: str
    target_area_sqm: float = 10.0
    area_tolerance: float = 0.25
    zone_preference: str = "center"
    preferred_orientation: str = ""
    preferred_position_hint: str = ""
    position_hint_x: float = 0.5
    position_hint_y: float = 0.5
    must_touch_outline: bool = False
    must_be_rectangle: bool = False
    aspect_min: float = 0.35
    aspect_max: float = 3.0
    priority: int = 50
    near_rooms: list[str] = Field(default_factory=list)
    avoid_rooms: list[str] = Field(default_factory=list)
    adjacency_required: list[str] = Field(default_factory=list)
    adjacency_preferred: list[str] = Field(default_factory=list)
    allow_non_rect: bool = True
    index: int = 1


class LayoutConstraintPlan(BaseModel):
    entrance_side: str = "bottom"
    public_side: str = "south"
    rooms: list[RoomPlacementConstraint] = Field(default_factory=list)
    adjacency_must: list[tuple[str, str]] = Field(default_factory=list)
    adjacency_prefer: list[tuple[str, str]] = Field(default_factory=list)
    adjacency_avoid: list[tuple[str, str]] = Field(default_factory=list)


class RoomPlacementResult(BaseModel):
    name: str
    room_type: str
    area_sqm: float
    is_rectangle: bool
    orientation: str = ""
    adjacent_rooms: list[str] = Field(default_factory=list)
    score_component: dict[str, float] = Field(default_factory=dict)
    cell_count: int = 0
    validation_status: str = "ok"


class LayoutSearchReport(BaseModel):
    total_score: float = 0.0
    hard_constraints_passed: bool = False
    violations: list[str] = Field(default_factory=list)
    unsatisfied_constraints: list[str] = Field(default_factory=list)
    room_results: list[RoomPlacementResult] = Field(default_factory=list)
    grid_assignment: list[list[int]] = Field(default_factory=list)
    repair_log: list[str] = Field(default_factory=list)
    explanation: str = ""
    planned_area_sqm: float = 0.0
    outline_area_sqm: float = 0.0
    area_coverage_ratio: float = 0.0
