"use client";

import { useState } from "react";

export function ActionBar({
  disabled,
  onRegeneratePlan,
  onRegenerateDraft
}: {
  disabled: boolean;
  onRegeneratePlan: (modificationRequest: string) => Promise<void>;
  onRegenerateDraft: () => Promise<void>;
}) {
  const [modification, setModification] = useState("");

  return (
    <div className="rounded-lg border bg-white p-4">
      <h3 className="text-sm font-semibold">操作区</h3>
      <div className="mt-2 flex gap-2">
        <input
          className="flex-1 rounded-md border px-3 py-2 text-sm"
          placeholder="输入修改需求，如：增加书房并保留南向客厅"
          value={modification}
          onChange={(e) => setModification(e.target.value)}
        />
        <button
          disabled={disabled || !modification.trim()}
          className="rounded-md bg-indigo-600 px-3 py-2 text-sm text-white disabled:opacity-60"
          onClick={() => onRegeneratePlan(modification)}
        >
          重新规划
        </button>
        <button
          disabled={disabled}
          className="rounded-md bg-emerald-600 px-3 py-2 text-sm text-white disabled:opacity-60"
          onClick={onRegenerateDraft}
        >
          重新绘图
        </button>
      </div>
    </div>
  );
}
