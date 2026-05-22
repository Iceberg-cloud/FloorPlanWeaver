"use client";

import { Icon } from "./Icon";
import type { PipelineStage } from "../lib/pipelineStages";

export function ThinkingPipeline({
  stages,
  activeIndex,
}: {
  stages: PipelineStage[];
  activeIndex: number;
}) {
  if (!stages.length) return null;

  return (
    <div className="fpw-pipeline rounded-xl border border-indigo-100 bg-gradient-to-br from-indigo-50/90 to-violet-50/80 p-3">
      <div className="mb-2 flex items-center gap-2">
        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 ai-thinking-glow">
          <Icon name="brain" size={12} className="text-indigo-600 ai-thinking-pulse" />
        </div>
        <div>
          <p className="text-[11px] font-semibold text-indigo-900">多智能体协作</p>
          <p className="text-[10px] text-indigo-600/80">正在按环节处理你的请求</p>
        </div>
      </div>

      <ol className="space-y-1.5">
        {stages.map((stage, idx) => {
          const done = idx < activeIndex;
          const active = idx === activeIndex;
          const pending = idx > activeIndex;

          return (
            <li
              key={stage.id}
              className={`fpw-pipeline-step flex items-start gap-2.5 rounded-lg px-2 py-1.5 transition-all ${
                active
                  ? "bg-white/80 shadow-sm ring-1 ring-indigo-200"
                  : done
                    ? "opacity-90"
                    : "opacity-50"
              }`}
            >
              <div
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
                  done
                    ? "bg-emerald-100 text-emerald-600"
                    : active
                      ? "bg-indigo-100 text-indigo-600 ai-thinking-glow"
                      : "bg-slate-100 text-slate-400"
                }`}
              >
                {done ? (
                  <Icon name="check" size={12} />
                ) : (
                  <Icon
                    name={stage.icon}
                    size={12}
                    className={active ? "ai-thinking-pulse" : ""}
                  />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[11px] font-semibold ${
                      active ? "text-indigo-800" : done ? "text-slate-700" : "text-slate-500"
                    }`}
                  >
                    {stage.label}
                  </span>
                  {active && (
                    <span className="fpw-pipeline-live flex items-center gap-1 text-[9px] font-medium text-indigo-600">
                      <span className="fpw-pipeline-live-dot" />
                      进行中
                    </span>
                  )}
                </div>
                <p className="text-[10px] leading-snug text-slate-500">{stage.hint}</p>
                <span className="text-[9px] text-slate-400">{stage.agent}</span>
              </div>
              {active && (
                <div className="ai-thinking-dots shrink-0 self-center">
                  <span />
                  <span />
                  <span />
                </div>
              )}
              {pending && (
                <span className="shrink-0 self-center text-[9px] text-slate-300">待开始</span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
