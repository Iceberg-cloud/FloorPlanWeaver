import { Icon } from "./Icon";
import {
  deriveRequirementProgress,
  fieldLabel,
} from "../lib/requirementProgress";

export function ProgressChecklist({
  collected,
  missing,
  collecting = false,
}: {
  collected: string[];
  missing: string[];
  collecting?: boolean;
}) {
  const { rows, filledCount, total, pct } = deriveRequirementProgress(
    collected,
    missing,
    collecting,
  );
  const stillAsking = collecting && missing.length > 0;

  return (
    <div className="fpw-card p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon name="clipboard" size={13} className="text-slate-400" />
          <h3 className="text-xs font-semibold text-slate-700">信息收集进度</h3>
        </div>
        <span
          className={`fpw-badge shrink-0 ${
            stillAsking ? "fpw-badge-warning" : pct === 100 ? "fpw-badge-success" : "fpw-badge-info"
          }`}
        >
          {stillAsking ? `收集中 ${filledCount}/${total}` : `${pct}%`}
        </span>
      </div>

      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            stillAsking
              ? "bg-gradient-to-r from-amber-400 to-indigo-500"
              : "bg-gradient-to-r from-indigo-500 to-emerald-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {stillAsking && (
        <p className="mt-1.5 text-[10px] text-amber-700">
          规划师还需补充 {missing.map(fieldLabel).join("、")}
        </p>
      )}

      <ul className="mt-2 space-y-1">
        {rows.map(({ key, label, done }) => (
          <li
            key={key}
            className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] ${
              done ? "bg-emerald-50 text-emerald-800" : "bg-amber-50/80 text-amber-900"
            }`}
          >
            <Icon
              name={done ? "check" : "alert"}
              size={10}
              className={done ? "text-emerald-600" : "text-amber-600"}
            />
            <span className="font-medium">{label}</span>
            <span className="ml-auto text-[10px] opacity-70">{done ? "已填" : "待补充"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
