"use client";

import { useState } from "react";
import { Icon } from "./Icon";

export type DrawMethod = "vector" | "multimodal" | "both";

export function ActionBar({
  disabled,
  drawMethod,
  onDrawMethodChange,
  onRegeneratePlan,
  onRegenerateDraft,
}: {
  disabled: boolean;
  drawMethod: DrawMethod;
  onDrawMethodChange: (method: DrawMethod) => void;
  onRegeneratePlan: (modificationRequest: string) => Promise<void>;
  onRegenerateDraft: () => Promise<void>;
}) {
  const [modification, setModification] = useState("");

  return (
    <div className="fpw-card p-3">
      <div className="flex items-center gap-2 mb-2">
        <Icon name="grid" size={13} className="text-slate-400" />
        <h3 className="text-xs font-semibold text-slate-700">绘图方式</h3>
      </div>

      {/* Method Selection */}
      <div className="mb-2 flex gap-1 rounded-lg bg-slate-100 p-0.5">
        <button
          className={`fpw-tab text-[10px] ${drawMethod === "vector" ? "fpw-tab-active" : ""}`}
          onClick={() => onDrawMethodChange("vector")}
        >
          <span className="flex items-center gap-1">
            <Icon name="layout" size={10} />
            A 矢量SVG
          </span>
        </button>
        <button
          className={`fpw-tab text-[10px] ${drawMethod === "multimodal" ? "fpw-tab-active" : ""}`}
          onClick={() => onDrawMethodChange("multimodal")}
        >
          <span className="flex items-center gap-1">
            <Icon name="sparkles" size={10} />
            B 多模态LLM
          </span>
        </button>
        <button
          className={`fpw-tab text-[10px] ${drawMethod === "both" ? "fpw-tab-active" : ""}`}
          onClick={() => onDrawMethodChange("both")}
        >
          <span className="flex items-center gap-1">
            A+B
          </span>
        </button>
      </div>

      <div className="mb-1 text-[10px] text-slate-400 leading-relaxed">
        {drawMethod === "vector" && "方法A：矢量布局，精确匹配外轮廓，使用SVG渲染"}
        {drawMethod === "multimodal" && "方法B：多模态LLM生成，效果更真实，不一定满足外轮廓"}
        {drawMethod === "both" && "同时生成两种方式，可对比查看"}
      </div>

      {/* Modify & regenerate */}
      <div className="flex gap-2 mt-2">
        <input
          className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs outline-none focus:border-indigo-400 focus:bg-white"
          placeholder="修改需求，如：增加书房"
          value={modification}
          onChange={(e) => setModification(e.target.value)}
        />
        <button
          disabled={disabled || !modification.trim()}
          className="fpw-icon-btn bg-indigo-600 text-white hover:bg-indigo-700"
          onClick={() => onRegeneratePlan(modification)}
        >
          <Icon name="refresh" size={12} />
        </button>
        <button
          disabled={disabled}
          className="fpw-icon-btn bg-emerald-600 text-white hover:bg-emerald-700"
          onClick={onRegenerateDraft}
        >
          <Icon name="image" size={12} />
        </button>
      </div>
    </div>
  );
}
