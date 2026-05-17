import type { PlannerAskForMore, PlannerFinalPlan } from "../lib/types";

export function PlanViewer({
  planner
}: {
  planner: PlannerAskForMore | PlannerFinalPlan | null;
}) {
  return (
    <div className="h-full rounded-lg border bg-white p-4">
      <h2 className="text-lg font-semibold">规划方案</h2>
      {!planner ? (
        <p className="mt-3 text-sm text-slate-500">等待生成规划方案...</p>
      ) : (
        <div className="mt-3">
          <p className="text-xs text-slate-500">Planner 状态：{planner.agent_state}</p>
          {"drawing_brief" in planner && (
            <p className="mt-2 rounded bg-slate-50 p-2 text-sm text-slate-700">{planner.drawing_brief}</p>
          )}
          {"follow_up_questions" in planner && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
              {planner.follow_up_questions.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          )}
          <pre className="mt-3 max-h-[70vh] overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-100">
            {JSON.stringify(planner, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
