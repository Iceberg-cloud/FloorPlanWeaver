"""Requirement working memory: merge, delta, preferences, planner context, reconcile."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from app.agents.planner_agent import PlannerAgent
from app.schemas.planner import PlannerFinalPlan, SpaceProgramItem

if TYPE_CHECKING:
    from app.schemas.layout import SiteOutline
    from app.schemas.session import ChatMessage

_AREA_MISMATCH_ABS_SQM = 2.0
_AREA_MISMATCH_RATIO = 0.05

_REQUIRED_KEYS = PlannerAgent.REQUIRED_KEYS

# ── Soft preference patterns (regex → preference text) ────────────
_PREFERENCE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"主卧.*?(要|想|希望|需要).{0,4}大"), "主卧要宽敞"),
    (re.compile(r"次卧.*?(要|想|希望|需要).{0,4}大"), "次卧要宽敞"),
    (re.compile(r"客厅.*?(要|想|希望|需要).{0,4}大"), "客厅要大"),
    (re.compile(r"厨房.*?(要|想|希望|需要).{0,4}大"), "厨房要大"),
    (re.compile(r"卫生间.*?(要|想|希望|需要).{0,4}大"), "卫生间要宽敞"),
    (re.compile(r"无障碍"), "需要无障碍设计"),
    (re.compile(r"老人"), "有老人居住"),
    (re.compile(r"小孩|儿童|孩子|宝宝"), "有小孩"),
    (re.compile(r"宠物|猫|狗"), "有宠物"),
    (re.compile(r"岛台"), "厨房要放岛台"),
    (re.compile(r"衣帽间"), "需要衣帽间"),
    (re.compile(r"干湿分离"), "卫生间干湿分离"),
    (re.compile(r"动静分离"), "动静分离"),
    (re.compile(r"南北通透"), "南北通透"),
    (re.compile(r"采光.*(好|充足|重要)"), "采光充足"),
    (re.compile(r"通风.*(好|充足|重要)"), "通风良好"),
    (re.compile(r"(要|想|希望|需要).{0,4}(一个|一间)?.{0,2}书房"), "需要书房"),
    (re.compile(r"(要|想|希望|需要).{0,4}(一个|一间)?.{0,2}储物"), "需要储物空间"),
    (re.compile(r"(主卧|卧室).{0,6}独卫"), "主卧带独卫"),
    (re.compile(r"玄关"), "需要玄关"),
    (re.compile(r"工作区|办公区|居家办公"), "需要居家办公区"),
    (re.compile(r"步入式"), "步入式衣柜/储物"),
]


def extract_user_preferences(text: str) -> list[str]:
    """Extract soft preferences from a user message using pattern matching."""
    prefs: list[str] = []
    for pattern, label in _PREFERENCE_PATTERNS:
        if pattern.search(text):
            prefs.append(label)
    return prefs


def merge_room_program(
    existing: list[dict],
    new_items: list[dict],
    *,
    layout_type: str = "",
) -> list[dict]:
    by_type: dict[str, dict] = {item["room_type"]: dict(item) for item in existing if item.get("room_type")}
    for item in new_items:
        if not isinstance(item, dict):
            continue
        rt = item.get("room_type", "")
        if not rt:
            continue
        if rt in by_type:
            by_type[rt].update({k: v for k, v in item.items() if k != "room_type" and v is not None})
        else:
            by_type[rt] = dict(item)
    return list(by_type.values())


def merge_adjacency_rules(existing: list[dict], new_items: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    merged: list[dict] = []
    for item in list(existing) + list(new_items):
        if not isinstance(item, dict):
            continue
        key = (str(item.get("source", "")), str(item.get("target", "")), str(item.get("relation", "")))
        if key in seen:
            continue
        seen.add(key)
        merged.append(dict(item))
    return merged


def merge_string_list(existing: list[str] | None, new_items: list[str] | None) -> list[str]:
    """Merge two string lists, deduplicating by exact match."""
    seen = set(existing or [])
    merged = list(existing or [])
    for item in (new_items or []):
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def apply_delta_to_memory(
    memory: dict,
    user_message: str,
    chat_history: list[ChatMessage] | None = None,
) -> dict:
    """Rule-based extraction from current user turn + history into working memory.

    Enhancements over plain single-message extraction:
    - Extracts soft preferences from both current message and recent history
    - Builds a conversation_summary from prior messages
    """
    merged = dict(memory or {})

    # 1. Core structured extraction from current message
    PlannerAgent()._extract_to_collected(user_message, merged)

    # 2. Extract soft preferences from current message
    new_prefs = extract_user_preferences(user_message)
    if new_prefs:
        existing_prefs = merged.get("user_preferences") or []
        merged["user_preferences"] = merge_string_list(existing_prefs, new_prefs)

    # 3. Extract soft preferences from recent history (if not already captured)
    if chat_history:
        for msg in chat_history[-6:]:
            if msg.role == "user" and msg.content.strip():
                hist_prefs = extract_user_preferences(msg.content)
                if hist_prefs:
                    existing_prefs = merged.get("user_preferences") or []
                    merged["user_preferences"] = merge_string_list(existing_prefs, hist_prefs)

    # 4. Build conversation summary from history (keep it short)
    if chat_history:
        summary_parts = []
        for msg in chat_history[-10:]:
            if msg.role == "user" and msg.content.strip():
                summary_parts.append(f"用户：{msg.content.strip()[:100]}")
            elif msg.role == "assistant" and msg.content.strip():
                summary_parts.append(f"助手：{msg.content.strip()[:80]}")
        if summary_parts:
            merged["conversation_summary"] = "\n".join(summary_parts[-12:])

    return merged


def merge_snapshot(base: dict, update: dict | None) -> dict:
    """Merge LLM/rule collected_snapshot into persisted working memory."""
    if not update:
        return dict(base or {})
    out = dict(base or {})
    for key, val in update.items():
        if val is None or val == "":
            continue
        if key == "room_program" and isinstance(val, list):
            out["room_program"] = merge_room_program(out.get("room_program") or [], val)
        elif key == "adjacency_rules" and isinstance(val, list):
            out["adjacency_rules"] = merge_adjacency_rules(out.get("adjacency_rules") or [], val)
        elif key == "user_preferences" and isinstance(val, list):
            out["user_preferences"] = merge_string_list(out.get("user_preferences"), val)
        else:
            out[key] = val
    return out


def compute_missing_fields(memory: dict) -> list[str]:
    return [key for key in _REQUIRED_KEYS if key not in memory or not memory[key]]


def build_requirement_progress(memory: dict) -> "ProgressSnapshot":
    """Canonical progress: only the five planner required keys."""
    from app.schemas.chat import ProgressSnapshot

    missing = compute_missing_fields(memory)
    collected = [key for key in _REQUIRED_KEYS if key not in missing]
    return ProgressSnapshot(collected_fields=collected, missing_fields=missing)


def filter_missing_fields(missing: list[str], memory: dict) -> list[str]:
    still = set(compute_missing_fields(memory))
    return [m for m in missing if m in still]


def snapshot_from_final_plan(plan: PlannerFinalPlan) -> dict:
    return {
        "building_type": plan.project_profile.building_type,
        "target_area_sqm": plan.project_profile.target_area_sqm,
        "layout_type": plan.project_profile.layout_type,
        "orientation": plan.project_profile.orientation,
        "room_program": [item.model_dump() for item in plan.space_program],
        "adjacency_rules": [item.model_dump() for item in plan.adjacency_graph],
        "design_goals": list(plan.design_goals or []),
        "lifestyle_tags": list(plan.lifestyle_tags or []),
        "episodic_summary": (plan.owner_summary.headline if plan.owner_summary else "") or plan.drawing_brief,
    }


def effective_outline_area_sqm(outline: SiteOutline | None) -> float | None:
    """Positive outline area from saved geometry, or None if unavailable."""
    if outline is None:
        return None
    from app.services.layout_metrics import outline_area_sqm

    area = outline_area_sqm(outline)
    return area if area > 0 else None


def _areas_differ(user_sqm: float, outline_sqm: float) -> bool:
    return abs(user_sqm - outline_sqm) > max(
        _AREA_MISMATCH_ABS_SQM,
        outline_sqm * _AREA_MISMATCH_RATIO,
    )


def align_memory_with_outline(
    memory: dict,
    outline: SiteOutline | None,
) -> tuple[dict, list[str]]:
    """When a site outline exists, use its area as the authoritative target_area_sqm."""
    merged = dict(memory or {})
    notices: list[str] = []
    outline_sqm = effective_outline_area_sqm(outline)
    if outline_sqm is None:
        return merged, notices

    outline_sqm = round(outline_sqm, 1)
    user_raw = merged.get("target_area_sqm")
    user_f: float | None = None
    if user_raw not in (None, ""):
        try:
            user_f = float(user_raw)
        except (TypeError, ValueError):
            user_f = None

    merged["target_area_sqm"] = outline_sqm
    merged["outline_area_sqm"] = outline_sqm
    if user_f is not None and _areas_differ(user_f, outline_sqm):
        notices.append(
            f"已以外轮廓面积 {outline_sqm:.1f}㎡ 为准（对话中的 {user_f:g}㎡ 与轮廓不一致，已忽略）。"
        )
    return merged, notices


def outline_reminder_notices(has_site_outline: bool) -> list[str]:
    if has_site_outline:
        return []
    return [
        "建议先在右侧「外轮廓编辑器」绘制并保存建筑外轮廓；"
        "布局将按轮廓实际面积生成（未绘制时仅按默认矩形估算，可能与口述面积不一致）。",
    ]


def scale_space_program_to_target(
    program: list[SpaceProgramItem],
    new_target_sqm: float,
    old_target_sqm: float | None,
) -> list[SpaceProgramItem]:
    old = float(old_target_sqm or 0)
    if old <= 0 or not program:
        return program
    if abs(new_target_sqm - old) <= max(1.0, old * 0.02):
        return program
    scale = new_target_sqm / old
    return [
        item.model_copy(
            update={
                "target_area_sqm": round(max(3.0, (item.target_area_sqm or 8) * scale), 1),
            }
        )
        for item in program
    ]


def reconcile_final_plan(
    plan: PlannerFinalPlan,
    collected: dict,
    outline: SiteOutline | None = None,
) -> PlannerFinalPlan:
    """Prefer confirmed working memory; outline area overrides stated building area."""
    if not collected and outline is None:
        return plan

    profile_updates: dict = {}
    if collected:
        profile_updates.update(
            {
                k: collected[k]
                for k in ("building_type", "target_area_sqm", "layout_type", "orientation")
                if collected.get(k) not in (None, "")
            }
        )

    outline_sqm = effective_outline_area_sqm(outline)
    if outline_sqm is not None:
        profile_updates["target_area_sqm"] = round(outline_sqm, 1)

    profile = plan.project_profile.model_copy(update=profile_updates) if profile_updates else plan.project_profile

    space_program = plan.space_program
    if collected.get("room_program"):
        space_program = [
            SpaceProgramItem.model_validate(item)
            for item in collected["room_program"]
            if isinstance(item, dict) and item.get("room_type")
        ]

    new_target = profile.target_area_sqm
    if new_target and plan.project_profile.target_area_sqm:
        space_program = scale_space_program_to_target(
            space_program or plan.space_program,
            float(new_target),
            float(plan.project_profile.target_area_sqm),
        )

    return plan.model_copy(
        update={
            "project_profile": profile,
            "space_program": space_program or plan.space_program,
        }
    )


def build_regenerate_user_message(
    latest_plan: PlannerFinalPlan,
    modification: str,
    memory: dict | None = None,
) -> str:
    snap = memory or snapshot_from_final_plan(latest_plan)
    prefs = (memory or {}).get("user_preferences") or []
    pref_text = f"。用户偏好：{'、'.join(prefs)}" if prefs else ""
    return (
        "在既有方案基础上修改。已确认需求快照："
        + json.dumps(snap, ensure_ascii=False)
        + f"。原方案摘要：{latest_plan.drawing_brief}{pref_text}。修改意见：{modification}"
    )


def build_planner_messages(
    *,
    working_memory: dict,
    user_message: str,
    chat_history: list[ChatMessage] | None = None,
    max_turns: int = 8,
) -> list[dict[str, str]]:
    """Multi-turn context for planner LLM with user preferences and conversation summary."""
    messages: list[dict[str, str]] = []
    history = list(chat_history or [])
    if max_turns > 0 and len(history) > max_turns * 2:
        history = history[-max_turns * 2 :]

    for msg in history:
        if msg.role in ("user", "assistant") and msg.content.strip():
            messages.append({"role": msg.role, "content": msg.content})

    # Build enriched context for current turn
    context_parts = ["【已确认需求快照】\n" + json.dumps(working_memory, ensure_ascii=False)]

    prefs = working_memory.get("user_preferences") or []
    if prefs:
        context_parts.append("【用户偏好】\n" + "、".join(prefs))

    conv_summary = working_memory.get("conversation_summary") or ""
    if conv_summary:
        context_parts.append("【历史对话摘要】\n" + conv_summary)

    context_parts.append("【本轮用户输入】\n" + user_message)

    messages.append({"role": "user", "content": "\n".join(context_parts)})
    return messages


def working_memory_summary(memory: dict) -> str:
    """Short text for episodic slot."""
    parts: list[str] = []
    if memory.get("layout_type"):
        parts.append(str(memory["layout_type"]))
    if memory.get("target_area_sqm"):
        parts.append(f"{memory['target_area_sqm']}㎡")
    if memory.get("building_type"):
        parts.append(str(memory["building_type"]))
    rooms = memory.get("room_program") or []
    if isinstance(rooms, list) and rooms:
        names = [r.get("room_type", "") for r in rooms if isinstance(r, dict)]
        parts.append("房间:" + "、".join(n for n in names if n))
    prefs = memory.get("user_preferences") or []
    if prefs:
        parts.append("偏好:" + "、".join(prefs[:5]))
    return " · ".join(parts) if parts else ""
