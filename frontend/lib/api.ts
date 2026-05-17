import type { ChatResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export async function createSession(): Promise<string> {
  const res = await fetch(`${API_BASE}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error("创建会话失败");
  const data = (await res.json()) as { session_id: string };
  return data.session_id;
}

export async function sendChat(sessionId: string, userMessage: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, user_message: userMessage })
  });
  if (!res.ok) throw new Error("发送消息失败");
  return (await res.json()) as ChatResponse;
}

export async function regeneratePlan(sessionId: string, modificationRequest: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/plan/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, modification_request: modificationRequest })
  });
  if (!res.ok) throw new Error("重新规划失败");
  return (await res.json()) as ChatResponse;
}

export async function regenerateDraft(sessionId: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/draft/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  });
  if (!res.ok) throw new Error("重新绘图失败");
  return (await res.json()) as ChatResponse;
}
