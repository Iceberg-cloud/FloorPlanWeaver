"""Owner summary and area validation for planner output."""

from __future__ import annotations

from app.schemas.planner import (
    AreaValidation,
    OwnerSummary,
    PlannerFinalPlan,
    RoomAreaRow,
)


def validate_area(plan: PlannerFinalPlan) -> AreaValidation:
    target = plan.project_profile.target_area_sqm or 0
    planned = sum(
        (item.target_area_sqm or 0) * max(1, item.count)
        for item in plan.space_program
    )
    ratio = (planned / target * 100) if target > 0 else 0
    deviation = abs(planned - target) / target * 100 if target > 0 else 0
    return AreaValidation(
        target_total_sqm=target,
        planned_total_sqm=planned,
        deviation_percent=round(deviation, 1),
        passed=0.9 * target <= planned <= 1.1 * target if target > 0 else True,
        message="",
    )


def build_owner_summary(plan: PlannerFinalPlan) -> OwnerSummary:
    profile = plan.project_profile
    area_validation = validate_area(plan)
    planned_total = area_validation.planned_total_sqm or 1.0
    room_rows = []
    for item in plan.space_program:
        subtotal = (item.target_area_sqm or 0) * max(1, item.count)
        ratio = (subtotal / planned_total * 100) if planned_total > 0 else 0
        room_rows.append(
            RoomAreaRow(
                room_type=item.room_type,
                count=item.count,
                area_sqm=round(subtotal, 1),
                ratio_percent=round(ratio, 1),
            )
        )
    headline = (
        f"{profile.building_type or '住宅'} · {profile.layout_type or '户型'}"
        f" · 建筑面积约 {profile.target_area_sqm or '待定'}㎡"
    )
    return OwnerSummary(headline=headline, room_rows=room_rows, area_validation=area_validation)


def enrich_final_plan(plan: PlannerFinalPlan) -> PlannerFinalPlan:
    plan.owner_summary = build_owner_summary(plan)
    return plan
