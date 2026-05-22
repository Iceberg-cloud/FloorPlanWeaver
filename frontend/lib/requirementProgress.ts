/** Mirrors backend PlannerAgent.REQUIRED_KEYS */
export const REQUIREMENT_FIELDS = [
  { key: "layout_type", label: "户型类型" },
  { key: "target_area_sqm", label: "建筑面积" },
  { key: "room_program", label: "房间清单" },
  { key: "orientation", label: "朝向偏好" },
  { key: "building_type", label: "建筑类型" },
] as const;

export type RequirementFieldKey = (typeof REQUIREMENT_FIELDS)[number]["key"];

export function fieldLabel(key: string): string {
  return REQUIREMENT_FIELDS.find((f) => f.key === key)?.label ?? key;
}

export type RequirementProgressUi = {
  rows: { key: RequirementFieldKey; label: string; done: boolean }[];
  filledCount: number;
  total: number;
  pct: number;
  collecting: boolean;
};

export function deriveRequirementProgress(
  collected: string[],
  missing: string[],
  collecting: boolean,
): RequirementProgressUi {
  const missingSet = new Set(missing);
  const collectedSet = new Set(collected);
  const rows = REQUIREMENT_FIELDS.map(({ key, label }) => {
    const done = collectedSet.has(key) && !missingSet.has(key);
    return { key, label, done };
  });
  const filledCount = rows.filter((r) => r.done).length;
  const total = REQUIREMENT_FIELDS.length;
  let pct = total > 0 ? Math.round((filledCount / total) * 100) : 0;
  if (collecting && missingSet.size > 0) {
    pct = Math.min(pct, 99);
  }
  return { rows, filledCount, total, pct, collecting };
}

export function defaultAskQuestions(missing: string[]): string[] {
  if (missing.includes("layout_type") && missing.includes("target_area_sqm")) {
    return ["请补充户型类型与建筑面积（例如：三居、约120㎡）；朝向与房间若有要求可一并说明。"];
  }
  const labels = missing.map(fieldLabel);
  if (labels.length > 0) {
    return [`请补充：${labels.join("、")}。`];
  }
  return ["请补充户型类型、建筑面积与房间需求（例如：三居、约120㎡）。"];
}

export function resolveAskQuestions(
  planner: { follow_up_questions?: string[]; missing_fields?: string[] },
): string[] {
  const qs = planner.follow_up_questions?.filter((q) => q && q.trim()) ?? [];
  if (qs.length > 0) return qs;
  return defaultAskQuestions(planner.missing_fields ?? []);
}
