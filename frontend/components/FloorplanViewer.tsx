"use client";

import { useEffect, useMemo, useState } from "react";
import { Icon } from "./Icon";
import type { DrawMethod } from "./ActionBar";
import type { DrawerDraft, LayoutOutput, LayoutRoom, SiteOutline } from "../lib/types";
import { normalizePolygonRing, polygonLabelCenter } from "../lib/polygonRender";

type Tab = "layout" | "drawer";

function resolveViewerMode(
  drawMethod: DrawMethod,
  hasLayout: boolean,
  hasDrawer: boolean,
  hasImage: boolean,
  tab: Tab,
): "layout" | "drawer" | "empty" | "drawer-missing-image" {
  if (!hasLayout && !hasDrawer) return "empty";
  if (drawMethod === "multimodal") {
    if (hasDrawer && hasImage) return "drawer";
    if (hasDrawer) return "drawer-missing-image";
    return "empty";
  }
  if (drawMethod === "vector") {
    return hasLayout ? "layout" : "empty";
  }
  if (tab === "drawer") {
    if (hasDrawer && hasImage) return "drawer";
    if (hasDrawer) return "drawer-missing-image";
    return hasLayout ? "layout" : "empty";
  }
  return hasLayout ? "layout" : hasDrawer && hasImage ? "drawer" : "empty";
}

export function FloorplanViewer({
  drawer,
  layout,
  outline,
  drawMethod,
  areaCoverage,
}: {
  drawer: DrawerDraft | null;
  layout: LayoutOutput | null;
  outline: SiteOutline | null;
  drawMethod: DrawMethod;
  areaCoverage?: { ratio?: number; planned?: number; outline?: number } | null;
}) {
  const layoutRooms = layout?.rooms ?? [];
  const hasLayout = layoutRooms.length > 0 || Boolean(layout?.svg_base64);
  const hasDrawer = drawer !== null;

  const imageSrc = useMemo(() => {
    if (!drawer) return null;
    if (drawer.image_base64) {
      const mime = drawer.image_mime_type || "image/png";
      const raw = drawer.image_base64.trim();
      if (raw.startsWith("data:")) return raw;
      return `data:${mime};base64,${raw}`;
    }
    if (drawer.image_url) return drawer.image_url;
    return null;
  }, [drawer]);

  const showTabs = drawMethod === "both" && (hasLayout || hasDrawer);
  const defaultTab: Tab = drawMethod === "multimodal" ? "drawer" : "layout";
  const [activeTab, setActiveTab] = useState<Tab>(defaultTab);

  useEffect(() => {
    setActiveTab(drawMethod === "multimodal" ? "drawer" : "layout");
  }, [drawMethod]);

  const viewMode = resolveViewerMode(
    drawMethod,
    hasLayout,
    hasDrawer,
    Boolean(imageSrc),
    activeTab,
  );

  return (
    <div className="fpw-card flex h-full flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-50">
          <Icon name="home" size={14} className="text-cyan-600" />
        </div>
        <h2 className="text-sm font-semibold text-slate-800">户型平面图</h2>

        {showTabs && (
          <div className="ml-auto flex gap-1 rounded-lg bg-slate-100 p-0.5">
            <button
              type="button"
              className={`fpw-tab ${activeTab === "layout" ? "fpw-tab-active" : ""}`}
              onClick={() => setActiveTab("layout")}
              disabled={!hasLayout}
            >
              <span className="flex items-center gap-1">
                <Icon name="layout" size={11} />
                方法A
              </span>
            </button>
            <button
              type="button"
              className={`fpw-tab ${activeTab === "drawer" ? "fpw-tab-active" : ""}`}
              onClick={() => setActiveTab("drawer")}
              disabled={!hasDrawer}
            >
              <span className="flex items-center gap-1">
                <Icon name="sparkles" size={11} />
                方法B
              </span>
            </button>
          </div>
        )}

        {!showTabs && (drawMethod === "vector" || drawMethod === "multimodal") && (
          <span className="ml-auto fpw-badge fpw-badge-info">
            {drawMethod === "vector" && "方法A 矢量SVG"}
            {drawMethod === "multimodal" && "方法B 多模态LLM"}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {viewMode === "empty" && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 shimmer-bg">
              <Icon name="home" size={22} className="text-slate-400" />
            </div>
            <p className="mt-3 text-sm text-slate-400">等待绘图结果...</p>
            <p className="mt-1 text-[10px] text-slate-300">
              {drawMethod === "vector" && "将使用矢量方法精确生成布局"}
              {drawMethod === "multimodal" && "将使用多模态LLM生成户型图"}
              {drawMethod === "both" && "将同时生成两种方式"}
            </p>
          </div>
        )}

        {viewMode === "layout" && hasLayout && (
          <div className="p-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50">
              <LayoutSvgRenderer layout={layout!} outline={outline} />
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span className="fpw-badge fpw-badge-success">
                <Icon name="check" size={10} /> 矢量布局
              </span>
              <span className="text-[10px] text-slate-400">
                {layoutRooms.length} 个房间 · {layout?.compile_method ?? "—"}
                {areaCoverage?.ratio != null && areaCoverage.planned != null && areaCoverage.outline != null && (
                  <> · 规划占比 {(areaCoverage.ratio * 100).toFixed(0)}%（{areaCoverage.planned}㎡/{areaCoverage.outline}㎡）</>
                )}
              </span>
            </div>
          </div>
        )}

        {viewMode === "drawer" && drawer && imageSrc && (
          <DrawerImagePanel drawer={drawer} imageSrc={imageSrc} />
        )}

        {viewMode === "drawer-missing-image" && drawer && (
          <div className="flex flex-col items-center justify-center gap-2 p-6 text-center">
            <p className="text-sm text-amber-700">多模态图像数据无效或无法加载</p>
            {drawer.image_url && (
              <a
                href={drawer.image_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-600 underline"
              >
                在新标签页打开原图
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DrawerImagePanel({ drawer, imageSrc }: { drawer: DrawerDraft; imageSrc: string }) {
  const [loadError, setLoadError] = useState(false);

  return (
    <div className="p-3">
      {loadError ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-center text-sm text-amber-800">
          浏览器无法直接显示该图片（可能被跨域策略拦截）。
          {drawer.image_url && (
            <a
              href={drawer.image_url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 block text-xs text-indigo-600 underline"
            >
              点击在新窗口查看
            </a>
          )}
        </div>
      ) : (
        <img
          src={imageSrc}
          alt="户型平面图"
          className="w-full rounded-lg object-contain"
          onError={() => setLoadError(true)}
        />
      )}
      <div className="mt-2 rounded-lg border border-slate-100 bg-slate-50 p-2">
        <div className="mb-1 flex items-center gap-2">
          <span className="fpw-badge fpw-badge-warning">
            <Icon name="sparkles" size={10} /> 多模态LLM
          </span>
          <span className="text-[10px] text-slate-400">{drawer.model}</span>
        </div>
        <p className="text-[10px] text-amber-600">
          注意：LLM生成的户型图不一定严格匹配外轮廓约束；矢量布置以方法A为准。
        </p>
        <details className="group mt-1">
          <summary className="flex cursor-pointer items-center gap-1 text-[10px] text-slate-400 hover:text-slate-600">
            <Icon name="pencil" size={9} /> 出图提示词
          </summary>
          <p className="mt-1 whitespace-pre-wrap break-words text-[10px] leading-relaxed text-slate-500">
            {drawer.image_prompt}
          </p>
        </details>
      </div>
    </div>
  );
}

function LayoutSvgRenderer({
  layout,
  outline,
}: {
  layout: LayoutOutput;
  outline: SiteOutline | null;
}) {
  const rooms = layout.rooms ?? [];
  const outlineVerts = outline?.vertices ?? layout.outline?.vertices ?? [];

  const allPts = rooms.flatMap((r) => r.pts ?? []).concat(outlineVerts);
  if (allPts.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-xs text-slate-400">
        暂无可用几何数据
      </div>
    );
  }
  const xs = allPts.map((p) => p.x);
  const ys = allPts.map((p) => p.y);
  const minX = Math.min(...xs, 0) - 0.5;
  const minY = Math.min(...ys, 0) - 0.5;
  const maxX = Math.max(...xs) + 0.5;
  const maxY = Math.max(...ys) + 0.5;
  const vw = maxX - minX || 1;
  const vh = maxY - minY || 1;

  const roomColors = [
    { fill: "#dbeafe", stroke: "#3b82f6" },
    { fill: "#fef3c7", stroke: "#f59e0b" },
    { fill: "#dcfce7", stroke: "#22c55e" },
    { fill: "#fce7f3", stroke: "#ec4899" },
    { fill: "#ede9fe", stroke: "#8b5cf6" },
    { fill: "#ffedd5", stroke: "#f97316" },
    { fill: "#cffafe", stroke: "#06b6d4" },
    { fill: "#f3e8ff", stroke: "#a855f7" },
    { fill: "#fef9c3", stroke: "#eab308" },
    { fill: "#d1fae5", stroke: "#10b981" },
    { fill: "#fee2e2", stroke: "#ef4444" },
    { fill: "#e0e7ff", stroke: "#6366f1" },
  ];

  return (
    <svg className="w-full" viewBox={`${minX} ${minY} ${vw} ${vh}`} style={{ maxHeight: "50vh" }}>
      {Array.from({ length: Math.ceil(maxX) + 1 }, (_, i) => (
        <line key={`gx${i}`} x1={i} y1={minY} x2={i} y2={maxY} stroke="#f1f5f9" strokeWidth="0.03" />
      ))}
      {Array.from({ length: Math.ceil(maxY) + 1 }, (_, i) => (
        <line key={`gy${i}`} x1={minX} y1={i} x2={maxX} y2={i} stroke="#f1f5f9" strokeWidth="0.03" />
      ))}

      {outlineVerts.length >= 3 && (
        <polygon
          points={outlineVerts.map((v) => `${v.x},${v.y}`).join(" ")}
          fill="rgba(148,163,184,0.05)"
          stroke="#475569"
          strokeWidth="0.1"
          strokeLinejoin="round"
        />
      )}

      {rooms.map((room, idx) => {
        const c = roomColors[idx % roomColors.length];
        return <RoomShape key={room.room_id} room={room} fill={c.fill} stroke={c.stroke} />;
      })}
    </svg>
  );
}

function RoomShape({ room, fill, stroke }: { room: LayoutRoom; fill: string; stroke: string }) {
  const pts = normalizePolygonRing(room.pts ?? []);
  if (pts.length < 3) return null;

  const { x: cx, y: cy } = polygonLabelCenter(pts);
  const isPoly = room.shape_kind === "polygon" || pts.length > 4;

  return (
    <g>
      <polygon
        points={pts.map((p) => `${p.x},${p.y}`).join(" ")}
        fill={fill}
        stroke={stroke}
        strokeWidth="0.06"
        strokeLinejoin="miter"
        strokeLinecap="square"
        fillRule="evenodd"
        vectorEffect="non-scaling-stroke"
        className={isPoly ? "fpw-room-poly" : "fpw-room-rect"}
      />
      <text x={cx} y={cy - 0.12} textAnchor="middle" fontSize="0.32" fill="#1e293b" fontWeight="600">
        {room.name}
      </text>
      <text x={cx} y={cy + 0.22} textAnchor="middle" fontSize="0.22" fill="#64748b">
        {room.area_sqm.toFixed(1)}㎡
      </text>
    </g>
  );
}
