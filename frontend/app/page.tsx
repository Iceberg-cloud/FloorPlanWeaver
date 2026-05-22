"use client";

import { useCallback, useEffect, useState } from "react";

import { ActionBar, type DrawMethod } from "../components/ActionBar";
import { ChatPanel } from "../components/ChatPanel";
import { FloorplanViewer } from "../components/FloorplanViewer";
import { Icon } from "../components/Icon";
import { OutlineEditor } from "../components/OutlineEditor";
import { PlanViewer } from "../components/PlanViewer";
import { ProgressChecklist } from "../components/ProgressChecklist";
import {
  beaconEndUserSession,
  createSession,
  endUserSession,
  getOutline,
  loadSession,
  regenerateDraft,
  regeneratePlan,
  saveOutline,
  sendChat,
  SESSION_STORAGE_KEY,
  shutdownServer,
} from "../lib/api";
import { normalizeDrawer } from "../lib/drawer";
import { normalizeLayout } from "../lib/layout";
import { normalizePlanner } from "../lib/planner";
import { resolveAskQuestions } from "../lib/requirementProgress";
import {
  getPipelineStages,
  stageAtIndex,
  type PipelineOperation,
  type PipelineStage,
} from "../lib/pipelineStages";
import type {
  ChatResponse,
  DrawerDraft,
  LayoutOutput,
  PlannerAskForMore,
  PlannerFinalPlan,
  SiteOutline,
} from "../lib/types";

type ChatMsg = { role: "user" | "assistant"; content: string };

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [planner, setPlanner] = useState<PlannerAskForMore | PlannerFinalPlan | null>(null);
  const [drawer, setDrawer] = useState<DrawerDraft | null>(null);
  const [layout, setLayout] = useState<LayoutOutput | null>(null);
  const [layoutCoverage, setLayoutCoverage] = useState<{
    ratio?: number;
    planned?: number;
    outline?: number;
  } | null>(null);
  const [outline, setOutline] = useState<SiteOutline | null>(null);
  const [drawMethod, setDrawMethod] = useState<DrawMethod>("vector");
  const [progress, setProgress] = useState<{ collected_fields: string[]; missing_fields: string[] }>({
    collected_fields: [],
    missing_fields: [],
  });
  const [plannerCollecting, setPlannerCollecting] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<string>("等待请求");
  const [pipelineStages, setPipelineStages] = useState<PipelineStage[]>([]);
  const [pipelineActiveIndex, setPipelineActiveIndex] = useState(0);
  const [runtimeErrorRaw, setRuntimeErrorRaw] = useState<string>("");
  const [showShutdownConfirm, setShowShutdownConfirm] = useState(false);
  const [shuttingDown, setShuttingDown] = useState(false);

  useEffect(() => {
    void ensureSession();
  }, []);

  const resetLocalUserState = useCallback(() => {
    setSessionId("");
    setMessages([]);
    setPlanner(null);
    setDrawer(null);
    setLayout(null);
    setLayoutCoverage(null);
    setOutline(null);
    setProgress({ collected_fields: [], missing_fields: [] });
    setPlannerCollecting(false);
    setRuntimeErrorRaw("");
    if (typeof window !== "undefined") {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    const onPageLeave = () => {
      const sid = sessionId || localStorage.getItem(SESSION_STORAGE_KEY);
      if (sid) {
        beaconEndUserSession(sid);
      } else {
        localStorage.removeItem(SESSION_STORAGE_KEY);
      }
    };
    window.addEventListener("pagehide", onPageLeave);
    return () => window.removeEventListener("pagehide", onPageLeave);
  }, [sessionId]);

  const beginThinking = useCallback((operation: PipelineOperation) => {
    const stages = getPipelineStages(operation, drawMethod);
    setPipelineStages(stages);
    setPipelineActiveIndex(0);
    const first = stageAtIndex(stages, 0);
    if (first) setRuntimeStatus(first.label);
  }, [drawMethod]);

  const clearThinking = useCallback(() => {
    setPipelineStages([]);
    setPipelineActiveIndex(0);
  }, []);

  useEffect(() => {
    if (!loading || pipelineStages.length === 0) return;

    setPipelineActiveIndex(0);
    const first = pipelineStages[0];
    if (first) setRuntimeStatus(first.label);

    const timeouts: ReturnType<typeof setTimeout>[] = [];
    let elapsed = 0;
    for (let i = 0; i < pipelineStages.length - 1; i++) {
      elapsed += pipelineStages[i].durationMs;
      const next = i + 1;
      const t = setTimeout(() => {
        setPipelineActiveIndex(next);
        setRuntimeStatus(pipelineStages[next].label);
      }, elapsed);
      timeouts.push(t);
    }

    return () => {
      timeouts.forEach(clearTimeout);
    };
  }, [loading, pipelineStages]);

  const hydrateFromServer = (dump: Awaited<ReturnType<typeof loadSession>>) => {
    if (!dump) return;
    const chatMsgs = dump.messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));
    if (chatMsgs.length > 0) setMessages(chatMsgs);
    const collected = Object.keys(dump.collected_requirements ?? {});
    if (collected.length > 0) {
      setProgress((p) => ({ ...p, collected_fields: collected.sort() }));
    }
    if (dump.latest_plan) {
      setPlanner(normalizePlanner(dump.latest_plan) ?? dump.latest_plan);
    }
    setPlannerCollecting(dump.planner_state === "collecting");
    if (dump.draw_method === "vector" || dump.draw_method === "multimodal" || dump.draw_method === "both") {
      setDrawMethod(dump.draw_method);
    }
    const restoredDrawer = normalizeDrawer(dump.latest_draft);
    if (restoredDrawer) setDrawer(restoredDrawer);
    const restoredLayout = normalizeLayout(dump.latest_layout);
    if (restoredLayout) setLayout(restoredLayout);
  };

  const ensureSession = async (): Promise<string | null> => {
    if (sessionId) return sessionId;
    try {
      const stored =
        typeof window !== "undefined" ? localStorage.getItem(SESSION_STORAGE_KEY) : null;
      if (stored) {
        const dump = await loadSession(stored);
        if (dump) {
          setSessionId(stored);
          const saved = await getOutline(stored);
          if (saved) setOutline(saved);
          hydrateFromServer(dump);
          setRuntimeStatus("已恢复历史会话");
          setRuntimeErrorRaw("");
          return stored;
        }
        localStorage.removeItem(SESSION_STORAGE_KEY);
      }

      const id = await createSession();
      setSessionId(id);
      if (typeof window !== "undefined") {
        localStorage.setItem(SESSION_STORAGE_KEY, id);
      }
      const saved = await getOutline(id);
      if (saved) setOutline(saved);
      setRuntimeStatus("会话已就绪");
      setRuntimeErrorRaw("");
      return id;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRuntimeStatus("会话初始化失败");
      setRuntimeErrorRaw(message);
      return null;
    }
  };

  const consumeResponse = (res: ChatResponse) => {
    const normalizedPlanner = normalizePlanner(res.planner) ?? res.planner;
    setPlanner(normalizedPlanner);
    setPlannerCollecting(res.status === "collecting");
    setProgress(res.progress);
    setRuntimeStatus(buildRuntimeStatusText(res, normalizedPlanner));
    setRuntimeErrorRaw(extractRuntimeError(res));
    if (res.status === "draft_failed") {
      setPlannerCollecting(false);
      setDrawer(null);
      setLayout(null);
    setLayoutCoverage(null);
      const errorText = res.runtime.drawer?.error ?? "未知错误";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `绘图阶段失败：${errorText}\n你可以修改需求后重试。`,
        },
      ]);
      return;
    }
    if (res.status === "completed") {
      setPlannerCollecting(false);
      if (res.drawer != null) {
        setDrawer(normalizeDrawer(res.drawer));
      } else if (drawMethod === "multimodal") {
        setDrawer(null);
      }
      const nextLayout = normalizeLayout(res.layout);
      if (nextLayout != null) {
        setLayout(nextLayout);
      } else if (drawMethod === "vector") {
        setLayout(null);
      }
      if (
        res.area_coverage_ratio != null &&
        res.planned_area_sqm != null &&
        res.outline_area_sqm != null
      ) {
        setLayoutCoverage({
          ratio: res.area_coverage_ratio,
          planned: res.planned_area_sqm,
          outline: res.outline_area_sqm,
        });
      } else {
        setLayoutCoverage(null);
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: buildCompletionMessage(res, drawMethod),
        },
      ]);
      return;
    }
    if (res.status === "collecting" && res.planner.agent_state === "ASK_FOR_MORE") {
      const askPlanner = (normalizedPlanner ?? res.planner) as PlannerAskForMore;
      const questions = resolveAskQuestions(askPlanner);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: questions.join("\n") },
      ]);
    }
  };

  const onSend = async (text: string) => {
    const sid = await ensureSession();
    if (!sid) return;
    setLoading(true);
    beginThinking("chat");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    try {
      const res = await sendChat(sid, text, drawMethod);
      consumeResponse(res);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRuntimeStatus("请求失败");
      setRuntimeErrorRaw(message);
    } finally {
      setLoading(false);
      clearThinking();
    }
  };

  const onRegeneratePlan = async (modificationRequest: string) => {
    const sid = await ensureSession();
    if (!sid) return;
    setLoading(true);
    beginThinking("regenerate_plan");
    setMessages((prev) => [...prev, { role: "user", content: `修改需求：${modificationRequest}` }]);
    try {
      const res = await regeneratePlan(sid, modificationRequest, drawMethod);
      consumeResponse(res);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRuntimeStatus("请求失败");
      setRuntimeErrorRaw(message);
    } finally {
      setLoading(false);
      clearThinking();
    }
  };

  const onRegenerateDraft = async () => {
    const sid = await ensureSession();
    if (!sid) return;
    setLoading(true);
    beginThinking("regenerate_draft");
    try {
      const res = await regenerateDraft(sid, drawMethod);
      consumeResponse(res);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRuntimeStatus("请求失败");
      setRuntimeErrorRaw(message);
    } finally {
      setLoading(false);
      clearThinking();
    }
  };

  const onSaveOutline = async (newOutline: SiteOutline) => {
    const sid = await ensureSession();
    if (!sid) return;
    try {
      await saveOutline(sid, newOutline);
      setOutline(newOutline);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRuntimeErrorRaw(`保存轮廓失败：${message}`);
    }
  };

  const onShutdown = async () => {
    setShuttingDown(true);
    setRuntimeStatus("正在清理对话记录并关闭服务...");
    const sid = sessionId || localStorage.getItem(SESSION_STORAGE_KEY);
    try {
      if (sid) {
        await endUserSession(sid);
      }
      resetLocalUserState();
      await shutdownServer(sid ?? undefined);
    } catch {
      resetLocalUserState();
    }
    setRuntimeStatus("服务已关闭，对话记录已清理");
    setShowShutdownConfirm(false);
    setShuttingDown(false);
    // Close the browser tab after a short delay
    setTimeout(() => {
      window.close();
      // If window.close() is blocked, show a message
      setRuntimeStatus("请手动关闭此页面");
    }, 1500);
  };

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="fpw-header-bar px-5 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/20 backdrop-blur-sm">
              <Icon name="home" size={18} className="text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold text-white tracking-wide">FloorPlanWeaver</h1>
              <p className="text-[10px] text-indigo-200">多智能体户型设计平台</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-lg bg-white/10 px-3 py-1.5 backdrop-blur-sm">
              <div className={`h-2 w-2 rounded-full ${
                loading ? "bg-amber-300 animate-pulse" :
                runtimeStatus.includes("失败") ? "bg-rose-400" :
                runtimeStatus.includes("就绪") ? "bg-emerald-400" :
                "bg-slate-300"
              }`} />
              <span className="text-xs text-white/90">{runtimeStatus}</span>
            </div>
            <span className="text-[10px] text-indigo-200 font-mono">
              {sessionId ? `${sessionId.slice(0, 8)}...` : "---"}
            </span>
            <button
              className="fpw-icon-btn bg-white/10 text-white hover:bg-white/20 backdrop-blur-sm"
              onClick={() => setShowShutdownConfirm(true)}
            >
              <Icon name="power" size={12} />
              <span className="text-xs">关闭</span>
            </button>
          </div>
        </div>
      </header>

      {/* Shutdown Confirmation Modal */}
      {showShutdownConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-100">
                <Icon name="alert" size={20} className="text-rose-500" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-800">确认关闭服务</h3>
                <p className="text-xs text-slate-500">此操作不可撤销</p>
              </div>
            </div>
            <p className="text-sm text-slate-600 leading-relaxed">
              关闭后将停止服务，并自动删除当前会话的对话记录与本地缓存。确定要关闭吗？
            </p>
            <div className="mt-5 flex gap-3">
              <button
                className="flex-1 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                onClick={() => setShowShutdownConfirm(false)}
                disabled={shuttingDown}
              >
                取消
              </button>
              <button
                className="flex-1 rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50 transition-colors"
                onClick={onShutdown}
                disabled={shuttingDown}
              >
                {shuttingDown ? (
                  <span className="flex items-center justify-center gap-2">
                    <Icon name="loading" size={14} />
                    关闭中...
                  </span>
                ) : (
                  "确认关闭"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Banner */}
      {runtimeErrorRaw && (
        <div className="mx-4 mt-2 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3">
          <Icon name="alert" size={16} className="mt-0.5 shrink-0 text-rose-500" />
          <div>
            <p className="text-xs font-semibold text-rose-700">运行错误</p>
            <pre className="mt-1 whitespace-pre-wrap break-words text-xs text-rose-800">
              {runtimeErrorRaw}
            </pre>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 min-h-0 p-4">
        <div className="grid h-full grid-cols-12 gap-3">
          {/* Left: Chat + Progress + Actions */}
          <div className="col-span-3 flex h-full flex-col gap-3">
            <div className="flex-1 min-h-0">
              <ChatPanel
                messages={messages}
                loading={loading}
                pipelineStages={pipelineStages}
                pipelineActiveIndex={pipelineActiveIndex}
                onSend={onSend}
              />
            </div>
            <ProgressChecklist
              collected={progress.collected_fields}
              missing={progress.missing_fields}
              collecting={plannerCollecting}
            />
            <ActionBar
              disabled={loading}
              drawMethod={drawMethod}
              onDrawMethodChange={setDrawMethod}
              onRegeneratePlan={onRegeneratePlan}
              onRegenerateDraft={onRegenerateDraft}
            />
          </div>

          {/* Center-Left: Outline Editor */}
          <div className="col-span-3">
            <OutlineEditor outline={outline} onSave={onSaveOutline} />
          </div>

          {/* Center-Right: Plan Viewer */}
          <div className="col-span-3">
            <PlanViewer planner={planner} />
          </div>

          {/* Right: Floorplan Viewer */}
          <div className="col-span-3">
            <FloorplanViewer
              drawer={drawer}
              layout={layout}
              outline={outline}
              drawMethod={drawMethod}
              areaCoverage={layoutCoverage}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function buildCompletionMessage(res: ChatResponse, method: DrawMethod): string {
  const parts: string[] = ["已生成规划方案"];
  if (res.layout && (method === "vector" || method === "both")) {
    parts.push("矢量布局 (方法A)");
  }
  if (res.drawer && (method === "multimodal" || method === "both")) {
    parts.push("多模态LLM图像 (方法B)");
  }
  return parts.join(" + ") + "，你可以继续提出修改意见。";
}

function buildRuntimeStatusText(
  res: ChatResponse,
  plannerPayload?: PlannerAskForMore | PlannerFinalPlan | null,
): string {
  const planner = res.runtime.planner;
  const drawer = res.runtime.drawer;
  const layout = res.runtime.layout;

  if (res.status === "collecting") {
    const ask =
      plannerPayload && plannerPayload.agent_state === "ASK_FOR_MORE"
        ? (plannerPayload as PlannerAskForMore)
        : null;
    const qs = ask ? resolveAskQuestions(ask) : [];
    const missing = res.progress.missing_fields?.length ?? 0;
    if (qs.length > 0) {
      return missing > 0
        ? `待补充 ${missing} 项 · 请查看对话中的追问`
        : "规划师需要更多信息 · 请查看对话";
    }
    return "规划师需要更多信息";
  }

  if (res.status === "draft_failed") {
    return (drawer?.error ?? "").includes("超时")
      ? "绘图超时"
      : "绘图失败";
  }

  const parts: string[] = [];
  if (planner.llm_succeeded) parts.push("规划师完成");
  else if (planner.fallback_to_rule) parts.push("规划师(规则)");
  if (res.layout) {
    if (layout?.llm_succeeded) parts.push("布局顾问+编译完成");
    else parts.push("矢量布局完成");
  }
  if (drawer?.llm_succeeded) parts.push("设计师完成");
  else if (drawer?.fallback_to_rule) parts.push("设计师(规则)");

  return parts.length > 0 ? parts.join(" · ") : "处理完成";
}

function extractRuntimeError(res: ChatResponse): string {
  return res.runtime.drawer?.error ?? res.runtime.planner.error ?? "";
}
