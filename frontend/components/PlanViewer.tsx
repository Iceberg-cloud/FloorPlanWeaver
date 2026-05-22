import { Icon } from "./Icon";

import type { PlannerAskForMore, PlannerFinalPlan } from "../lib/types";
import { resolveAskQuestions } from "../lib/requirementProgress";



type Circulation = {

  main_route?: string;

  secondary_routes?: string[];

  principle?: string;

  bedroom_access?: string;

  service_access?: string;

};



type Zoning = {

  public_zone?: string[];

  private_zone?: string[];

  service_zone?: string[];

  principle?: string;

};



function asCirculation(raw: unknown): Circulation | null {

  if (!raw || typeof raw !== "object") return null;

  return raw as Circulation;

}



function asZoning(raw: unknown): Zoning | null {

  if (!raw || typeof raw !== "object") return null;

  return raw as Zoning;

}



export function PlanViewer({

  planner,

}: {

  planner: PlannerAskForMore | PlannerFinalPlan | null;

}) {

  const isFinal = planner?.agent_state === "FINAL_PLAN";
  const isAsk = planner?.agent_state === "ASK_FOR_MORE";
  const askQuestions =
    isAsk && planner ? resolveAskQuestions(planner as PlannerAskForMore) : [];

  const final = isFinal ? (planner as PlannerFinalPlan) : null;

  const circulation = final ? asCirculation(final.circulation) : null;

  const zoning = final ? asZoning(final.zoning) : null;



  return (

    <div className="fpw-card flex h-full flex-col overflow-hidden">

      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">

        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-50">

          <Icon name="clipboard" size={14} className="text-amber-600" />

        </div>

        <h2 className="text-sm font-semibold text-slate-800">规划方案</h2>

        {planner && (

          <span className={`ml-auto fpw-badge ${isFinal ? "fpw-badge-success" : "fpw-badge-info"}`}>

            {isFinal ? "已生成" : "收集中"}

          </span>

        )}

      </div>



      <div className="flex-1 overflow-y-auto px-4 py-3">

        {!planner ? (

          <div className="flex flex-col items-center justify-center py-8 text-center">

            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 shimmer-bg">

              <Icon name="clipboard" size={22} className="text-slate-400" />

            </div>

            <p className="mt-3 text-sm text-slate-400">等待生成规划方案...</p>

          </div>

        ) : (

          <div className="space-y-3">

            {isFinal && circulation && (circulation.main_route || circulation.principle) && (

              <div className="rounded-lg border border-violet-200 bg-gradient-to-br from-violet-50 to-indigo-50 p-3">

                <div className="flex items-center gap-1.5 mb-2">

                  <Icon name="layout" size={12} className="text-violet-600" />

                  <span className="text-xs font-semibold text-violet-800">动线规划</span>

                </div>

                {circulation.main_route && (

                  <div className="mb-2 rounded-md bg-white/70 px-2.5 py-2 border border-violet-100">

                    <p className="text-[10px] font-medium text-violet-600 mb-0.5">主路径</p>

                    <p className="text-xs text-violet-900 leading-relaxed font-medium">

                      {circulation.main_route}

                    </p>

                  </div>

                )}

                {circulation.secondary_routes && circulation.secondary_routes.length > 0 && (

                  <ul className="space-y-1 mb-2">

                    {circulation.secondary_routes.map((route, i) => (

                      <li

                        key={i}

                        className="flex gap-1.5 text-[11px] text-violet-800 leading-snug"

                      >

                        <span className="shrink-0 text-violet-400">·</span>

                        {route}

                      </li>

                    ))}

                  </ul>

                )}

                {circulation.principle && (

                  <p className="text-[10px] text-violet-700/90 italic border-t border-violet-100 pt-2">

                    {circulation.principle}

                  </p>

                )}

                {circulation.bedroom_access && (

                  <p className="text-[10px] text-violet-600 mt-1">{circulation.bedroom_access}</p>

                )}

                {circulation.service_access && (

                  <p className="text-[10px] text-violet-600 mt-0.5">{circulation.service_access}</p>

                )}

              </div>

            )}



            {isFinal && zoning && (

              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">

                <div className="flex items-center gap-1.5 mb-2">

                  <Icon name="layout" size={12} className="text-slate-500" />

                  <span className="text-xs font-semibold text-slate-700">功能分区</span>

                </div>

                <div className="grid grid-cols-3 gap-1.5 text-[10px]">

                  {zoning.public_zone && zoning.public_zone.length > 0 && (

                    <div className="rounded bg-sky-50 border border-sky-100 px-2 py-1.5">

                      <p className="font-semibold text-sky-700">公共</p>

                      <p className="text-sky-600">{zoning.public_zone.join("、")}</p>

                    </div>

                  )}

                  {zoning.private_zone && zoning.private_zone.length > 0 && (

                    <div className="rounded bg-emerald-50 border border-emerald-100 px-2 py-1.5">

                      <p className="font-semibold text-emerald-700">私密</p>

                      <p className="text-emerald-600">{zoning.private_zone.join("、")}</p>

                    </div>

                  )}

                  {zoning.service_zone && zoning.service_zone.length > 0 && (

                    <div className="rounded bg-amber-50 border border-amber-100 px-2 py-1.5">

                      <p className="font-semibold text-amber-700">服务</p>

                      <p className="text-amber-600">{zoning.service_zone.join("、")}</p>

                    </div>

                  )}

                </div>

              </div>

            )}



            {final?.drawing_brief && (

              <div className="rounded-lg bg-amber-50 border border-amber-100 p-3">

                <div className="flex items-center gap-1.5 mb-1.5">

                  <Icon name="sparkles" size={12} className="text-amber-500" />

                  <span className="text-xs font-semibold text-amber-700">设计摘要</span>

                </div>

                <p className="text-xs text-amber-800 leading-relaxed whitespace-pre-wrap">

                  {final.drawing_brief}

                </p>

              </div>

            )}



            {isAsk && askQuestions.length > 0 && (

              <div className="rounded-lg bg-blue-50 border border-blue-100 p-3">

                <div className="flex items-center gap-1.5 mb-1.5">

                  <Icon name="chat" size={12} className="text-blue-500" />

                  <span className="text-xs font-semibold text-blue-700">待您补充</span>

                </div>

                <ul className="space-y-1">

                  {askQuestions.map((q, i) => (

                    <li key={i} className="text-xs text-blue-800 leading-relaxed flex gap-1.5">

                      <span className="shrink-0 text-blue-400">{i + 1}.</span>

                      {q}

                    </li>

                  ))}

                </ul>

              </div>

            )}



            {final?.space_program && final.space_program.length > 0 && (

              <div>

                <div className="flex items-center gap-1.5 mb-2">

                  <Icon name="grid" size={12} className="text-slate-400" />

                  <span className="text-xs font-semibold text-slate-600">空间规划</span>

                </div>

                <div className="grid grid-cols-2 gap-1.5">

                  {final.space_program.map((room: Record<string, unknown>, i: number) => (

                    <div key={i} className="rounded-lg border border-slate-100 bg-slate-50 p-2">

                      <p className="text-xs font-semibold text-slate-700">{String(room.room_type ?? "")}</p>

                      <p className="text-[10px] text-slate-400">

                        {String(room.count ?? 1)}间 · {String(room.target_area_sqm ?? "-")}㎡

                      </p>

                    </div>

                  ))}

                </div>

              </div>

            )}



            <details className="group">

              <summary className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400 hover:text-slate-600 transition-colors">

                <Icon name="layout" size={10} />

                <span>查看完整 JSON</span>

                <svg className="h-3 w-3 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">

                  <polyline points="9 18 15 12 9 6" />

                </svg>

              </summary>

              <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-slate-900 p-3 text-[10px] text-slate-300">

                {JSON.stringify(planner, null, 2)}

              </pre>

            </details>

          </div>

        )}

      </div>

    </div>

  );

}


