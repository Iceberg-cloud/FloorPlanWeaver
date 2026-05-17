"use client";

import { useState } from "react";

type Message = { role: "user" | "assistant"; content: string };

export function ChatPanel({
  messages,
  loading,
  onSend
}: {
  messages: Message[];
  loading: boolean;
  onSend: (text: string) => Promise<void>;
}) {
  const [input, setInput] = useState("");

  return (
    <div className="flex h-full flex-col rounded-lg border bg-white p-4">
      <h2 className="text-lg font-semibold">需求对话</h2>
      <div className="mt-3 flex-1 space-y-3 overflow-y-auto">
        {messages.map((message, idx) => (
          <div
            key={`${message.role}-${idx}`}
            className={`rounded-md px-3 py-2 text-sm ${
              message.role === "user" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-900"
            }`}
          >
            {message.content}
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          className="flex-1 rounded-md border px-3 py-2 text-sm outline-none focus:border-slate-500"
          placeholder="输入你的户型需求..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button
          className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-60"
          disabled={loading || !input.trim()}
          onClick={async () => {
            const content = input.trim();
            setInput("");
            await onSend(content);
          }}
        >
          发送
        </button>
      </div>
    </div>
  );
}
