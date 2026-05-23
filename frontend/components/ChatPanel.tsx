"use client";

import { useRef, useEffect, useState } from "react";
import { Icon } from "./Icon";
import { ThinkingPipeline } from "./ThinkingPipeline";
import type { PipelineStage } from "../lib/pipelineStages";

type Message = { role: "user" | "assistant"; content: string };

/** Collapse middle history when conversation exceeds this count */
const HISTORY_COLLAPSE_AT = 8;
/** Keep this many latest messages visible while collapsed */
const VISIBLE_TAIL = 5;

const TEMPLATES = [
  {
    label: "三口之家",
    icon: "home" as const,
    prompt: "三室两厅住宅，120㎡，南向，三口之家居住，需要主卧、两个次卧、客厅、餐厅、厨房、两个卫生间、阳台",
  },
  {
    label: "两代同住",
    icon: "layout" as const,
    prompt: "四室两厅住宅，140㎡，南向，三代同堂，需要主卧套间、两个次卧、一个书房兼客房、客厅、餐厅、厨房、两个卫生间、大阳台，动静分离",
  },
  {
    label: "一人公寓",
    icon: "grid" as const,
    prompt: "一室一厅公寓，60㎡，南向采光，单身居住，需要卧室、客餐厅一体、开放式厨房、卫生间、阳台，紧凑实用",
  },
  {
    label: "两居刚需",
    icon: "clipboard" as const,
    prompt: "两室一厅住宅，80㎡，南向，年轻夫妻居住，需要主卧、次卧可做书房、客厅、厨房、一个卫生间、阳台",
  },
  {
    label: "改善大平层",
    icon: "home" as const,
    prompt: "四室两厅大平层，160㎡，南北通透，改善型住宅，需要主卧套间带独卫和衣帽间、两个次卧、书房、大客厅、餐厅、中西厨、两个卫生间、大阳台、玄关储物",
  },
];

export function ChatPanel({
  messages,
  loading,
  pipelineStages = [],
  pipelineActiveIndex = 0,
  hasSiteOutline = false,
  onSend,
}: {
  messages: Message[];
  loading: boolean;
  pipelineStages?: PipelineStage[];
  pipelineActiveIndex?: number;
  /** False when user has not saved a custom site outline yet */
  hasSiteOutline?: boolean;
  onSend: (text: string) => Promise<void>;
}) {
  const [input, setInput] = useState("");
  const [showTemplates, setShowTemplates] = useState(true);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const canCollapseHistory = messages.length > HISTORY_COLLAPSE_AT;
  const hiddenCount = canCollapseHistory
    ? Math.max(0, messages.length - VISIBLE_TAIL)
    : 0;
  const visibleMessages = canCollapseHistory && historyCollapsed
    ? messages.slice(-VISIBLE_TAIL)
    : messages;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // Hide templates after first user message
  useEffect(() => {
    if (messages.some((m) => m.role === "user")) {
      setShowTemplates(false);
    }
  }, [messages]);

  useEffect(() => {
    if (messages.length > HISTORY_COLLAPSE_AT) {
      setHistoryCollapsed(true);
    }
  }, [messages.length]);

  return (
    <div className="fpw-card flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-50">
          <Icon name="chat" size={14} className="text-indigo-600" />
        </div>
        <h2 className="text-sm font-semibold text-slate-800">需求对话</h2>
        {messages.length > 0 && (
          <button
            className="ml-auto text-[10px] text-indigo-500 hover:text-indigo-700 transition-colors"
            onClick={() => setShowTemplates(!showTemplates)}
          >
            {showTemplates ? "收起模板" : "快捷模板"}
          </button>
        )}
      </div>

      {!hasSiteOutline && (
        <div className="border-b border-amber-100 bg-amber-50/90 px-4 py-2.5">
          <div className="flex gap-2">
            <Icon name="layout" size={14} className="mt-0.5 shrink-0 text-amber-600" />
            <p className="text-[11px] leading-relaxed text-amber-900">
              请先在右侧<strong className="font-semibold">外轮廓编辑器</strong>绘制并保存建筑外轮廓。
              已保存轮廓时，系统以<strong className="font-semibold">轮廓实际面积</strong>为准（与对话中口述面积不一致时会自动采用轮廓面积）。
            </p>
          </div>
        </div>
      )}

      {/* Template Quick Buttons */}
      {showTemplates && (
        <div className="border-b border-slate-100 px-4 py-2">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Icon name="sparkles" size={11} className="text-amber-500" />
            <span className="text-[10px] font-semibold text-slate-500">快捷模板</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {TEMPLATES.map((t) => (
              <button
                key={t.label}
                className="flex items-center gap-1 rounded-lg bg-gradient-to-r from-indigo-50 to-violet-50 px-2.5 py-1.5 text-[11px] font-medium text-indigo-700 hover:from-indigo-100 hover:to-violet-100 transition-all border border-indigo-100"
                disabled={loading}
                onClick={() => {
                  setInput(t.prompt);
                  inputRef.current?.focus();
                }}
              >
                <Icon name={t.icon} size={10} className="text-indigo-500" />
                {t.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages — min-h-0 enables wheel scroll inside flex column */}
      <div
        ref={scrollRef}
        className="fpw-chat-scroll min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-y-contain px-4 py-3"
      >
        {canCollapseHistory && (
          <button
            type="button"
            className="sticky top-0 z-10 mx-auto flex w-full max-w-[240px] items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white/95 py-1.5 text-[11px] font-medium text-slate-600 shadow-sm backdrop-blur hover:bg-slate-50"
            onClick={() => setHistoryCollapsed((v) => !v)}
          >
            <Icon name={historyCollapsed ? "chevron-down" : "chevron-up"} size={12} />
            {historyCollapsed
              ? `展开 ${hiddenCount} 条历史对话`
              : "收起较早对话"}
          </button>
        )}

        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center py-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
              <Icon name="home" size={22} className="text-slate-400" />
            </div>
            <p className="mt-3 text-sm text-slate-400">点击上方模板填入输入框</p>
            <p className="mt-1 text-xs text-slate-300">确认后点击发送，或直接输入需求</p>
          </div>
        )}
        {visibleMessages.map((message, idx) => {
          const globalIdx =
            canCollapseHistory && historyCollapsed
              ? messages.length - visibleMessages.length + idx
              : idx;
          return (
          <div key={`${message.role}-${globalIdx}`} className="flex gap-2">
            {message.role === "assistant" && (
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-50 mt-1">
                <Icon name="bot" size={12} className="text-indigo-500" />
              </div>
            )}
            <div
              className={
                message.role === "user"
                  ? "fpw-bubble-user ml-auto max-w-[85%]"
                  : "fpw-bubble-assistant max-w-[85%]"
              }
            >
              {message.content}
            </div>
            {message.role === "user" && (
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white border border-slate-200 mt-1">
                <Icon name="user" size={12} className="text-slate-500" />
              </div>
            )}
          </div>
          );
        })}

        {loading && pipelineStages.length > 0 && (
          <ThinkingPipeline stages={pipelineStages} activeIndex={pipelineActiveIndex} />
        )}
        {loading && pipelineStages.length === 0 && (
          <div className="flex gap-2">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-50 mt-1 ai-thinking-glow">
              <Icon name="brain" size={12} className="text-indigo-500 ai-thinking-pulse" />
            </div>
            <div className="ai-thinking-indicator">
              <div className="ai-thinking-dots">
                <span />
                <span />
                <span />
              </div>
              <span className="text-xs font-medium text-indigo-600">AI 正在思考...</span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-slate-100 px-4 py-3">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none transition-colors focus:border-indigo-400 focus:bg-white"
            placeholder="输入或编辑户型需求，确认后发送..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && input.trim() && !loading) {
                const content = input.trim();
                setInput("");
                void onSend(content);
              }
            }}
          />
          <button
            className="fpw-icon-btn bg-indigo-600 text-white hover:bg-indigo-700"
            disabled={loading || !input.trim()}
            onClick={async () => {
              const content = input.trim();
              setInput("");
              await onSend(content);
            }}
          >
            <Icon name="send" size={14} />
            <span className="hidden sm:inline">发送</span>
          </button>
        </div>
      </div>
    </div>
  );
}
