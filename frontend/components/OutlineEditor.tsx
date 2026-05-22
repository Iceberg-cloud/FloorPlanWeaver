"use client";

import { useCallback, useRef, useState } from "react";
import { Icon } from "./Icon";
import type { Point2D, SiteOutline } from "../lib/types";

const PRESETS = [
  { label: "矩形 80㎡", w: 11.2, h: 7.14 },
  { label: "矩形 100㎡", w: 12.5, h: 8.0 },
  { label: "矩形 120㎡", w: 14.0, h: 8.57 },
  { label: "矩形 140㎡", w: 15.0, h: 9.33 },
  {
    label: "L形 100㎡",
    vertices: [
      { x: 0, y: 0 }, { x: 14, y: 0 }, { x: 14, y: 5 },
      { x: 7, y: 5 }, { x: 7, y: 10 }, { x: 0, y: 10 },
    ],
  },
  {
    label: "T形 120㎡",
    vertices: [
      { x: 0, y: 0 }, { x: 16, y: 0 }, { x: 16, y: 4 },
      { x: 11, y: 4 }, { x: 11, y: 10 }, { x: 5, y: 10 },
      { x: 5, y: 4 }, { x: 0, y: 4 },
    ],
  },
];

interface ViewState {
  cx: number; // center x
  cy: number; // center y
  scale: number; // meters per pixel-ish unit (larger = zoomed out)
}

export function OutlineEditor({
  outline,
  onSave,
}: {
  outline: SiteOutline | null;
  onSave: (outline: SiteOutline) => void;
}) {
  const [vertices, setVertices] = useState<Point2D[]>(outline?.vertices ?? []);
  const [customW, setCustomW] = useState("12");
  const [customH, setCustomH] = useState("8");
  const svgRef = useRef<SVGSVGElement>(null);

  // View state: center + scale
  const [view, setView] = useState<ViewState>({ cx: 7, cy: 5, scale: 1.0 });

  const vb = computeViewBox(view, vertices);

  // Correct coordinate mapping using SVG CTM
  const svgPoint = useCallback((e: React.MouseEvent<SVGSVGElement>): Point2D | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const svgPt = pt.matrixTransform(ctm.inverse());
    return { x: +svgPt.x.toFixed(2), y: +svgPt.y.toFixed(2) };
  }, []);

  const addVertex = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    const pt = svgPoint(e);
    if (pt) setVertices((prev) => [...prev, pt]);
  }, [svgPoint]);

  const handleWheel = useCallback((e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const pt = svgPoint(e);
    const zoomFactor = e.deltaY < 0 ? 0.9 : 1.1;
    setView((prev) => {
      const newScale = Math.max(0.3, Math.min(5.0, prev.scale * zoomFactor));
      if (pt) {
        // Zoom toward cursor position
        const dx = pt.x - prev.cx;
        const dy = pt.y - prev.cy;
        const ratio = 1 - zoomFactor;
        return {
          cx: prev.cx + dx * ratio * 0.3,
          cy: prev.cy + dy * ratio * 0.3,
          scale: newScale,
        };
      }
      return { ...prev, scale: newScale };
    });
  }, [svgPoint]);

  // Pan with middle mouse or shift+drag
  const [panStart, setPanStart] = useState<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const handleMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
      e.preventDefault();
      setPanStart({ x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy });
    }
  }, [view]);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (panStart && svgRef.current) {
      const svg = svgRef.current;
      const rect = svg.getBoundingClientRect();
      const halfW = rect.width / 2;
      const halfH = rect.height / 2;
      const metersPerPixel = vb.w / rect.width;
      const dx = (e.clientX - panStart.x) * metersPerPixel;
      const dy = (e.clientY - panStart.y) * metersPerPixel;
      setView((prev) => ({ ...prev, cx: panStart.cx - dx, cy: panStart.cy - dy }));
    }
  }, [panStart, vb.w]);

  const handleMouseUp = useCallback(() => {
    setPanStart(null);
  }, []);

  const removeLastVertex = () => setVertices((prev) => prev.slice(0, -1));
  const clearVertices = () => setVertices([]);
  const resetView = () => setView({ cx: 7, cy: 5, scale: 1.0 });

  const applyPreset = (preset: typeof PRESETS[number]) => {
    let newVerts: Point2D[];
    if ("vertices" in preset && preset.vertices) {
      newVerts = preset.vertices;
    } else {
      newVerts = [
        { x: 0, y: 0 }, { x: preset.w!, y: 0 },
        { x: preset.w!, y: preset.h! }, { x: 0, y: preset.h! },
      ];
    }
    setVertices(newVerts);
    // Auto-fit view
    const xs = newVerts.map((v) => v.x);
    const ys = newVerts.map((v) => v.y);
    setView({
      cx: (Math.min(...xs) + Math.max(...xs)) / 2,
      cy: (Math.min(...ys) + Math.max(...ys)) / 2,
      scale: 1.0,
    });
  };

  const applyCustom = () => {
    const w = parseFloat(customW) || 12;
    const h = parseFloat(customH) || 8;
    setVertices([{ x: 0, y: 0 }, { x: w, y: 0 }, { x: w, y: h }, { x: 0, y: h }]);
    setView({ cx: w / 2, cy: h / 2, scale: 1.0 });
  };

  const handleSave = () => {
    if (vertices.length < 3) return;
    onSave(buildOutline(vertices));
  };

  const area = computeArea(vertices);

  // Grid lines based on view
  const gridLines = [];
  const gridStep = view.scale < 0.6 ? 2 : 1;
  for (let x = Math.floor(vb.x / gridStep) * gridStep; x <= vb.x + vb.w; x += gridStep) {
    gridLines.push(<line key={`gx${x}`} x1={x} y1={vb.y} x2={x} y2={vb.y + vb.h} stroke="#e2e8f0" strokeWidth="0.03" />);
  }
  for (let y = Math.floor(vb.y / gridStep) * gridStep; y <= vb.y + vb.h; y += gridStep) {
    gridLines.push(<line key={`gy${y}`} x1={vb.x} y1={y} x2={vb.x + vb.w} y2={y} stroke="#e2e8f0" strokeWidth="0.03" />);
  }

  return (
    <div className="fpw-card flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-50">
          <Icon name="layout" size={14} className="text-violet-600" />
        </div>
        <h2 className="text-sm font-semibold text-slate-800">外轮廓编辑器</h2>
        {outline && (
          <span className="ml-auto fpw-badge fpw-badge-success">
            <Icon name="check" size={10} /> 已保存
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {/* Presets */}
        <div className="flex flex-wrap gap-1">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-indigo-50 hover:text-indigo-600 transition-colors"
              onClick={() => applyPreset(p)}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Custom size */}
        <div className="mt-2 flex items-center gap-2">
          <input
            className="w-14 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs outline-none focus:border-indigo-400"
            placeholder="宽m"
            value={customW}
            onChange={(e) => setCustomW(e.target.value)}
          />
          <span className="text-xs text-slate-400">×</span>
          <input
            className="w-14 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs outline-none focus:border-indigo-400"
            placeholder="高m"
            value={customH}
            onChange={(e) => setCustomH(e.target.value)}
          />
          <button className="rounded-lg bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-100 transition-colors" onClick={applyCustom}>
            应用
          </button>
        </div>

        {/* SVG Canvas */}
        <div
          className="mt-2 rounded-lg border border-slate-200 bg-white"
          style={{ height: "calc(100% - 90px)", minHeight: "200px" }}
        >
          <svg
            ref={svgRef}
            className="h-full w-full"
            viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
            onClick={(e) => {
              if (!panStart) addVertex(e);
            }}
            onWheel={handleWheel}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            style={{ cursor: panStart ? "grabbing" : "crosshair" }}
          >
            {/* Grid */}
            {gridLines}

            {/* Axis labels */}
            {Array.from({ length: Math.ceil(vb.x + vb.w) + 1 }, (_, i) => i).filter(
              (i) => i >= Math.floor(vb.x) && i <= Math.ceil(vb.x + vb.w) && i % gridStep === 0
            ).map((i) => (
              <text key={`lx${i}`} x={i} y={vb.y + 0.3} fontSize="0.25" fill="#94a3b8" textAnchor="middle">{i}m</text>
            ))}

            {/* Outline polygon */}
            {vertices.length >= 3 && (
              <polygon
                points={vertices.map((v) => `${v.x},${v.y}`).join(" ")}
                fill="rgba(139,92,246,0.06)"
                stroke="#8b5cf6"
                strokeWidth="0.06"
              />
            )}
            {vertices.length >= 2 && (
              <polyline
                points={vertices.map((v) => `${v.x},${v.y}`).join(" ")}
                fill="none"
                stroke="#a78bfa"
                strokeWidth="0.04"
                strokeDasharray="0.15,0.08"
              />
            )}

            {/* Vertices with snap indication */}
            {vertices.map((v, i) => (
              <g key={i}>
                <circle cx={v.x} cy={v.y} r="0.18" fill="white" stroke="#7c3aed" strokeWidth="0.05" />
                <circle cx={v.x} cy={v.y} r="0.08" fill="#7c3aed" />
                <text
                  x={v.x + 0.2}
                  y={v.y - 0.15}
                  fontSize="0.2"
                  fill="#6d28d9"
                >
                  {`(${v.x},${v.y})`}
                </text>
              </g>
            ))}

            {/* Dimension labels on edges */}
            {vertices.length >= 2 && vertices.map((v, i) => {
              const next = vertices[(i + 1) % vertices.length];
              if (i >= vertices.length - 1 && vertices.length < 3) return null;
              const mx = (v.x + next.x) / 2;
              const my = (v.y + next.y) / 2;
              const dist = Math.sqrt((next.x - v.x) ** 2 + (next.y - v.y) ** 2);
              return (
                <text
                  key={`d${i}`}
                  x={mx}
                  y={my - 0.15}
                  fontSize="0.2"
                  fill="#a78bfa"
                  textAnchor="middle"
                >
                  {dist.toFixed(1)}m
                </text>
              );
            })}
          </svg>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2">
        <div className="text-xs text-slate-400">
          {vertices.length} 顶点 · {area.toFixed(1)} ㎡
          <span className="ml-2 text-[10px]">滚轮缩放 · Shift+拖拽平移</span>
        </div>
        <div className="flex gap-1.5">
          <button className="fpw-icon-btn bg-slate-100 text-slate-600 hover:bg-slate-200" onClick={resetView} title="重置视图">
            <Icon name="refresh" size={11} />
          </button>
          <button className="fpw-icon-btn bg-slate-100 text-slate-600 hover:bg-slate-200" onClick={removeLastVertex} title="撤销">
            <Icon name="undo" size={11} />
          </button>
          <button className="fpw-icon-btn bg-slate-100 text-slate-600 hover:bg-slate-200" onClick={clearVertices} title="清空">
            <Icon name="trash" size={11} />
          </button>
          <button
            className="fpw-icon-btn bg-indigo-600 text-white hover:bg-indigo-700"
            disabled={vertices.length < 3}
            onClick={handleSave}
          >
            <Icon name="save" size={11} />
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

function computeViewBox(view: ViewState, vertices: Point2D[]) {
  const halfSpan = 8 * view.scale;
  const w = halfSpan * 2;
  const h = halfSpan * 2;

  // If no vertices, use default center
  if (vertices.length === 0) {
    return { x: view.cx - halfSpan, y: view.cy - halfSpan, w, h };
  }

  return {
    x: view.cx - halfSpan,
    y: view.cy - halfSpan,
    w,
    h,
  };
}

function computeArea(vertices: Point2D[]): number {
  if (vertices.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < vertices.length; i++) {
    const j = (i + 1) % vertices.length;
    area += vertices[i].x * vertices[j].y;
    area -= vertices[j].x * vertices[i].y;
  }
  return Math.abs(area) / 2;
}

function buildOutline(vertices: Point2D[]): SiteOutline {
  const xs = vertices.map((v) => v.x);
  const ys = vertices.map((v) => v.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  return {
    vertices,
    entrance_edge: [0, 1],
    total_area_sqm: +computeArea(vertices).toFixed(1),
    bounding_box: { width: +(maxX - minX).toFixed(2), height: +(maxY - minY).toFixed(2) },
    unit: "meter",
  };
}
