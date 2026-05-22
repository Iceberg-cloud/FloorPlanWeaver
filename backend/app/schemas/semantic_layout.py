"""Semantic layout plan: AI outputs zones/bands only, no coordinates."""

from typing import Literal

from pydantic import BaseModel, Field

Zone = Literal[
    "north",
    "south",
    "east",
    "west",
    "center",
    "near_entrance",
    "far_from_entrance",
]

SizeClass = Literal["large", "medium", "small"]
LayoutStyle = Literal["strip"]
StripDirection = Literal["horizontal", "vertical"]
Cluster = Literal["public", "private", "service", "other"]


class RoomPlacement(BaseModel):
    room_type: str
    zone: Zone = "center"
    size: SizeClass = "medium"
    cluster: Cluster = "other"
    prefer_edge: str = ""
    near: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    index: int = 1
    # Normalized in outline bounding box (0=left/bottom, 1=right/top)
    center_x: float = Field(default=0.5, ge=0.0, le=1.0)
    center_y: float = Field(default=0.5, ge=0.0, le=1.0)
    width_ratio: float = Field(default=0.25, ge=0.05, le=1.0)
    height_ratio: float = Field(default=0.25, ge=0.05, le=1.0)


class LayoutBand(BaseModel):
    order: list[str] = Field(default_factory=list)


class AdjacencyIntent(BaseModel):
    a: str
    b: str
    strength: Literal["must", "prefer", "avoid"] = "prefer"


class SemanticLayoutPlan(BaseModel):
    layout_style: LayoutStyle = "strip"
    strip_direction: StripDirection = "horizontal"
    public_side: str = "south"
    entrance_room: str = ""
    placements: list[RoomPlacement] = Field(default_factory=list)
    bands: list[LayoutBand] = Field(default_factory=list)
    adjacency_intent: list[AdjacencyIntent] = Field(default_factory=list)
