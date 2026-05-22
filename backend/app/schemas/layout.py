from typing import Literal

from pydantic import BaseModel, Field


class Point2D(BaseModel):
    x: float
    y: float


class SiteOutline(BaseModel):
    vertices: list[Point2D] = Field(min_length=3)
    entrance_edge: list[int] = Field(default_factory=lambda: [0, 1])
    total_area_sqm: float = 0.0
    bounding_box: dict[str, float] = Field(default_factory=dict)
    unit: str = "meter"


class LayoutRoom(BaseModel):
    id: str
    name: str
    type: str = ""
    polygon: list[Point2D] = Field(min_length=3)
    area_sqm: float = 0.0
    adjacent_to: list[str] = Field(default_factory=list)
    shape_kind: Literal["rect", "polygon"] = "rect"


class LayoutDoor(BaseModel):
    between: list[str] = Field(default_factory=list)
    position: Point2D = Field(default_factory=lambda: Point2D(x=0, y=0))
    width: float = 0.9
    type: str = "swing"


class LayoutWindow(BaseModel):
    room: str = ""
    position: Point2D = Field(default_factory=lambda: Point2D(x=0, y=0))
    width: float = 1.2


class LayoutDraft(BaseModel):
    canvas: dict[str, float] = Field(default_factory=dict)
    outline_vertices: list[Point2D] = Field(default_factory=list)
    entrance_edge: list[int] = Field(default_factory=list)
    rooms: list[LayoutRoom] = Field(default_factory=list)
    doors: list[LayoutDoor] = Field(default_factory=list)
    windows: list[LayoutWindow] = Field(default_factory=list)
    compile_method: Literal["grid", "grid_search", "legacy"] = "legacy"


class LayoutValidationResult(BaseModel):
    hard_constraints_passed: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LayoutOutput(BaseModel):
    drawing_state: Literal["LAYOUT_READY"] = "LAYOUT_READY"
    render_source: Literal[
        "layout_llm", "layout_rule", "layout_semantic", "layout_greedy", "grid_search"
    ] = "layout_rule"
    layout: LayoutDraft = Field(default_factory=LayoutDraft)
    svg_base64: str = ""
    validation: LayoutValidationResult = Field(default_factory=LayoutValidationResult)
    notes: list[str] = Field(default_factory=list)
    area_coverage_ratio: float | None = None
    planned_area_sqm: float | None = None
    outline_area_sqm: float | None = None
