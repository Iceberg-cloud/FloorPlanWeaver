"use client";

import { useEffect, useState } from "react";

import { ActionBar } from "../components/ActionBar";
import { ChatPanel } from "../components/ChatPanel";
import { FloorplanSvgViewer } from "../components/FloorplanSvgViewer";
import { PlanViewer } from "../components/PlanViewer";
import { ProgressChecklist } from "../components/ProgressChecklist";
import { createSession, regenerateDraft, regeneratePlan, sendChat } from "../lib/api";
import type { ChatResponse, DrawerDraft, PlannerAskForMore, PlannerFinalPlan } from "../lib/types";

type ChatMsg = { role: "user" | "assistant"; content: string };

export default function HomePage() {
  const [sessionId, setSessionId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [planner, setPlanner] = useState<PlannerAskForMore | PlannerFinalPlan | null>(null);
  const [drawer, setDrawer] = useState<DrawerDraft | null>(null);
  const [progress, setProgress] = useState<{ collected_fields: string[]; missing_fields: string[] }>({
    collected_fields: [],
    missing_fields: []
  });
  const [runtimeStatus, setRuntimeStatus] = useState<string>("等待请求");
  const [runtimeErrorRaw, setRuntimeErrorRaw] = useState<string>("");

  useEffect(() => {
    void ensureSession();
  }, []);

  const ensureSession = async (): Promise<string | null> => {
    if (sessionId) return sessionId;
    try {
      const id = await createSession();
      setSessionId(id);
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
    setPlanner(res.planner);
    setProgress(res.progress);
    setRuntimeStatus(buildRuntimeStatusText(res));
    setRuntimeErrorRaw(extractRuntimeError(res));
    if (res.status === "draft_failed") {
      setDrawer(null);
      const errorText = res.runtime.drawer?.error ?? "未知错误";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `绘图阶段失败：${errorText}\n你可以修改需求后重试，或检查模型配置。`
        }
      ]);
      return;
    }
    if (res.status === "completed") {
      setDrawer(res.drawer ?? null);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "已生成规划方案与户型图，你可以继续提出修改意见。"
        }
      ]);
      return;
    }
    if ("follow_up_questions" in res.planner && res.planner.follow_up_questions.length > 0) {
      setMessages((prev) => [...prev, { role: "assistant", content: res.planner.follow_up_questions.join("\n") }]);
    }
  };

  const onSend = async (text: string) => {
    const sid = await ensureSession();
    if (!sid) return;
    setLoading(true);
    setRuntimeStatus("正在调用 LLM / 规则引擎...");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    try {
      const res = await sendChat(sid, text);
      consumeResponse(res);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRuntimeStatus("请求失败");
      setRuntimeErrorRaw(message);
    } finally {
      setLoading(false);
    }
  };

  const onRegeneratePlan = async (modificationRequest: string) => {
    const sid = await ensureSession();
    if (!sid) return;
    setLoading(true);
    setRuntimeStatus("正在调用 LLM / 规则引擎...");
    setMessages((prev) => [...prev, { role: "user", content: `修改需求：${modificationRequest}` }]);
    try {
      const res = await regeneratePlan(sid, modificationRequest);
      consumeResponse(res);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRuntimeStatus("请求失败");
      setRuntimeErrorRaw(message);
    } finally {
      setLoading(false);
    }
  };

  const onRegenerateDraft = async () => {
    const sid = await ensureSession();
    if (!sid) return;
    setLoading(true);
    setRuntimeStatus("正在调用 LLM / 规则引擎...");
    try {
      const res = await regenerateDraft(sid);
      consumeResponse(res);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRuntimeStatus("请求失败");
      setRuntimeErrorRaw(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="h-screen p-4">
      <div className="mb-3">
        <h1 className="text-xl font-bold">FloorPlanWeaver 多智能体 Demo</h1>
        <p className="text-sm text-slate-500">Session: {sessionId || "初始化中..."}</p>
        <p className="mt-1 text-sm text-indigo-700">运行状态：{runtimeStatus}</p>
        {runtimeErrorRaw ? (
          <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 p-2">
            <p className="text-xs font-semibold text-rose-700">错误原文</p>
            <pre className="mt-1 whitespace-pre-wrap break-words text-xs text-rose-900">
              {runtimeErrorRaw}
            </pre>
          </div>
        ) : null}
      </div>
      <div className="grid h-[calc(100%-44px)] grid-cols-12 gap-3">
        <div className="col-span-3 flex h-full flex-col gap-3">
          <ChatPanel messages={messages} loading={loading} onSend={onSend} />
          <ProgressChecklist collected={progress.collected_fields} missing={progress.missing_fields} />
          <ActionBar disabled={loading} onRegeneratePlan={onRegeneratePlan} onRegenerateDraft={onRegenerateDraft} />
        </div>
        <div className="col-span-4 h-full">
          <PlanViewer planner={planner} />
        </div>
        <div className="col-span-5 h-full">
          <FloorplanSvgViewer drawer={drawer} />
        </div>
      </div>
    </main>
  );
}

function buildRuntimeStatusText(res: ChatResponse): string {
  const planner = res.runtime.planner;
  const drawer = res.runtime.drawer;

  if (res.status === "draft_failed") {
    if ((drawer?.error ?? "").includes("超时")) {
      return "Drawer: LLM 调用超时，绘图失败（未回退）";
    }
    return "Drawer: LLM 调用失败，绘图失败（未回退）";
  }

  if (planner.fallback_to_rule) {
    if ((planner.error ?? "").includes("超时")) {
      return "Planner: LLM 调用超时，已回退规则模式";
    }
    return "Planner: LLM 调用失败，已回退规则模式";
  }

  if (drawer?.fallback_to_rule) {
    if ((drawer.error ?? "").includes("超时")) {
      return "Drawer: LLM 调用超时，已回退规则模式";
    }
    return "Drawer: LLM 调用失败，已回退规则模式";
  }

  if (planner.llm_attempted && planner.llm_succeeded) {
    if (drawer?.llm_attempted && drawer.llm_succeeded) {
      return "Planner/Drawer: LLM 调用成功";
    }
    return "Planner: LLM 调用成功";
  }

  return "规则模式已执行";
}

function extractRuntimeError(res: ChatResponse): string {
  const drawerError = res.runtime.drawer?.error;
  if (drawerError) return drawerError;
  const plannerError = res.runtime.planner.error;
  if (plannerError) return plannerError;
  return "";
}
