import type { ChatResponse, PlannerAskForMore, PlannerFinalPlan, SiteOutline } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
export const SESSION_STORAGE_KEY = "floorplan_weaver_session_id";

/** Delete server-side session (messages, plans, layout drafts). */
export async function endUserSession(sessionId: string): Promise<void> {
  if (!sessionId) return;
  try {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/end`, {
      method: "POST",
    });
    if (!res.ok && res.status !== 404) {
      throw new Error("结束会话失败");
    }
  } catch {
    try {
      await fetch(`${API_BASE}/sessions/${sessionId}`, { method: "DELETE" });
    } catch {
      /* best effort on tab close */
    }
  }
  if (typeof window !== "undefined") {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }
}

export function beaconEndUserSession(sessionId: string): void {
  if (!sessionId || typeof navigator === "undefined") return;
  navigator.sendBeacon(`${API_BASE}/sessions/${sessionId}/end`, new Blob([], { type: "application/json" }));
  localStorage.removeItem(SESSION_STORAGE_KEY);
}

export type SessionDump = {
  messages: { role: "user" | "assistant" | "system"; content: string }[];
  collected_requirements: Record<string, unknown>;
  planner_state: string;
  draw_method?: string;
  latest_plan: PlannerAskForMore | PlannerFinalPlan | null;
  latest_draft?: Record<string, unknown> | null;
  latest_layout?: Record<string, unknown> | null;
};

export async function createSession(): Promise<string> {
  const res = await fetch(`${API_BASE}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error("创建会话失败");
  const data = (await res.json()) as { session_id: string };
  return data.session_id;
}

export async function loadSession(sessionId: string): Promise<SessionDump | null> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
  if (!res.ok) return null;
  return (await res.json()) as SessionDump;
}

export async function getOutline(sessionId: string): Promise<SiteOutline | null> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/outline`);
  if (!res.ok) return null;
  const data = (await res.json()) as { status: string; outline?: SiteOutline };
  return data.outline ?? null;
}

export async function saveOutline(sessionId: string, outline: SiteOutline): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/outline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(outline),
  });
  if (!res.ok) throw new Error("保存外轮廓失败");
}

export async function sendChat(
  sessionId: string,
  userMessage: string,
  drawMethod: string = "auto",
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      user_message: userMessage,
      draw_method: drawMethod,
    }),
  });
  if (!res.ok) throw new Error("发送消息失败");
  return (await res.json()) as ChatResponse;
}

export async function regeneratePlan(
  sessionId: string,
  modificationRequest: string,
  drawMethod: string = "auto",
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/plan/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      modification_request: modificationRequest,
      draw_method: drawMethod,
    }),
  });
  if (!res.ok) throw new Error("重新规划失败");
  return (await res.json()) as ChatResponse;
}

export async function regenerateDraft(sessionId: string, drawMethod: string = "auto"): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/draft/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, draw_method: drawMethod }),
  });
  if (!res.ok) throw new Error("重新绘图失败");
  return (await res.json()) as ChatResponse;
}

export async function shutdownServer(sessionId?: string): Promise<void> {
  try {
    await fetch(`${API_BASE}/system/shutdown`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId ?? null }),
    });
  } catch {
    // Server is shutting down, so the request may fail
  }
  if (typeof window !== "undefined") {
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }
}
