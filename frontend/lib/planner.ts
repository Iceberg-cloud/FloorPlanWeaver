import type { PlannerAskForMore, PlannerFinalPlan } from "./types";
import { defaultAskQuestions } from "./requirementProgress";

/** Normalize partial planner JSON from API (defensive, mirrors backend coerce). */
export function normalizePlanner(
  raw: unknown,
): PlannerAskForMore | PlannerFinalPlan | null {
  if (!raw || typeof raw !== "object") return null;
  const p = raw as Record<string, unknown>;
  const state = String(p.agent_state ?? "");

  if (state === "ASK_FOR_MORE") {
    const missing = Array.isArray(p.missing_fields)
      ? (p.missing_fields as string[])
      : [];
    let questions = Array.isArray(p.follow_up_questions)
      ? (p.follow_up_questions as string[]).filter((q) => q && String(q).trim())
      : [];
    if (questions.length === 0) {
      questions = defaultAskQuestions(missing);
    }
    return {
      agent_state: "ASK_FOR_MORE",
      missing_fields: missing,
      follow_up_questions: questions,
      collected_snapshot:
        p.collected_snapshot && typeof p.collected_snapshot === "object"
          ? (p.collected_snapshot as Record<string, unknown>)
          : {},
    };
  }

  if (state === "FINAL_PLAN") {
    return p as PlannerFinalPlan;
  }

  return null;
}
