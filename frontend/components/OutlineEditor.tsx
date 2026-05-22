"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

type DrawMode = "free" | "orthogonal";
type EditorTool = "draw" | "select";

interface ViewState {
  cx: number;
  cy: number;
  scale: number;
}

// Grid snap: round to nearest 0.25m
const GRID_SNAP = 0.25;
const CLOSE_THRESHOLD = 0.5; // meters — click within this to close polygon
const VERTEX_HIT_RADIUS = 0.35;

function snapToGrid(val: number): number {
  return Math.round(val / GRID_SNAP) * GRID_SNAP;
}

function gridSnapPoint(pt: Point2D): Point2D {
  return { x: +snapToGrid(pt.x).toFixed(2), y: +snapToGrid(pt.y).toFixed(2) };
}

/** Snap a candidate point to be orthogonal relative to `prev`.
 *  Picks the axis (horizontal or vertical) with the larger delta. */
function orthogonalSnap(prev: Point2D, candidate: Point2D): Point2D {
  const dx = Math.abs(candidate.x - prev.x);
  const dy = Math.abs(candidate.y - prev.y);
  if (dx >= dy) {
    return { x: candidate.x, y: prev.y };
  }
  return { x: prev.x, y: candidate.y };
}

function dist(a: Point2D, b: Point2D): number {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
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
  const [drawMode, setDrawMode] = useState<DrawMode>("orthogonal");
  const [tool, setTool] = useState<EditorTool>("draw");
  const [mousePos, setMousePos] = useState<Point2D | null>(null);
  const [isClosed, setIsClosed] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const [view, setView] = useState<ViewState>({ cx: 7, cy: 5, scale: 1.0 });
  const [panStart, setPanStart] = useState<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const vb = computeViewBox(view, vertices);

  const svgPoint = useCallback((e: React.MouseEvent<SVGSVGElement>): Point2D | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const svgPt = pt.matrixTransform(ctm.inverse());
    return gridSnapPoint({ x: svgPt.x, y: svgPt.y });
  }, []);

  // Compute preview point for orthogonal mode
  const getPreviewPoint = useCallback((raw: Point2D): Point2D => {
    if (drawMode === "orthogonal" && vertices.length > 0) {
      return orthogonalSnap(vertices[vertices.length - 1], raw);
    }
    return raw;
  }, [drawMode, vertices]);

  const addVertex = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (tool !== "draw" || isClosed) return;
    const raw = svgPoint(e);
    if (!raw) return;

    // Check if clicking near the first vertex to close the polygon
    if (vertices.length >= 3) {
      if (dist(raw, vertices[0]) < CLOSE_THRESHOLD) {
        setIsClosed(true);
        return;
      }
    }

    const pt = getPreviewPoint(raw);
    setVertices((prev) => [...prev, pt]);
  }, [svgPoint, tool, isClosed, vertices, getPreviewPoint]);

  // Handle vertex dragging in select mode
  const handleSvgMouseDown = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    // Pan with middle button or Shift+left
    if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
      e.preventDefault();
      setPanStart({ x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy });
      return;
    }

    if (tool !== "select" || e.button !== 0) return;

    const raw = svgPoint(e);
    if (!raw) return;

    // Find closest vertex
    for (let i = 0; i < vertices.length; i++) {
      if (dist(raw, vertices[i]) < VERTEX_HIT_RADIUS) {
        setDragIndex(i);
        e.stopPropagation();
        return;
      }
    }
  }, [svgPoint, tool, vertices, view]);

  const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    const pt = svgPoint(e);
    setMousePos(pt);

    // Handle panning
    if (panStart && svgRef.current) {
      const svg = svgRef.current;
      const rect = svg.getBoundingClientRect();
      const metersPerPixel = vb.w / rect.width;
      const dx = (e.clientX - panStart.x) * metersPerPixel;
      const dy = (e.clientY - panStart.y) * metersPerPixel;
      setView((prev) => ({ ...prev, cx: panStart.cx - dx, cy: panStart.cy - dy }));
      return;
    }

    // Handle vertex dragging
    if (dragIndex !== null && pt) {
      setVertices((prev) => {
        const updated = [...prev];
        updated[dragIndex] = pt;
        return updated;
      });
    }
  }, [svgPoint, panStart, vb.w, dragIndex]);

  const handleMouseUp = useCallback(() => {
    setPanStart(null);
    setDragIndex(null);
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const pt = svgPoint(e);
    const zoomFactor = e.deltaY < 0 ? 0.9 : 1.1;
    setView((prev) => {
      const newScale = Math.max(0.3, Math.min(5.0, prev.scale * zoomFactor));
      if (pt) {
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

  const removeLastVertex = () => {
    setVertices((prev) => prev.slice(0, -1));
    setIsClosed(false);
  };
  const clearVertices = () => { setVertices([]); setIsClosed(false); };
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
    setIsClosed(true);
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
    setIsClosed(true);
    setView({ cx: w / 2, cy: h / 2, scale: 1.0 });
  };

  const handleSave = () => {
    if (vertices.length < 3) return;
    onSave(buildOutline(vertices));
  };

  const area = computeArea(vertices);

  // Preview point for drawing
  let previewPoint: Point2D | null = null;
  if (tool === "draw" && !isClosed && mousePos && vertices.length > 0) {
    previewPoint = getPreviewPoint(mousePos);
  }

  // Is mouse near first vertex (for close indicator)?
  const nearFirst = tool === "draw" && !isClosed && vertices.length >= 3 && mousePos
    ? dist(mousePos, vertices[0]) < CLOSE_THRESHOLD
    : false;

  // Grid lines
  const gridLines = [];
  const gridStep = view.scale < 0.6 ? 2 : 1;
  for (let x = Math.floor(vb.x / gridStep) * gridStep; x <= vb.x + vb.w; x += gridStep) {
    gridLines.push(<line key={`gx${x}`} x1={x} y1={vb.y} x2={x} y2={vb.y + vb.h} stroke="#e2e8f0" strokeWidth="0.03" />);
  }
  for (let y = Math.floor(vb.y / gridStep) * gridStep; y <= vb.y + vb.h; y += gridStep) {
    gridLines.push(<line key={`gy${y}`} x1={vb.x} y1={y} x2={vb.x + vb.w} y2={y} stroke="#e2e8f0" strokeWidth="0.03" />);
  }

  // Build polygon points string (closed if enough vertices)
  const polyPoints = vertices.map((v) => `${v.x},${v.y}`).join(" ");

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

        {/* Tool & Draw mode */}
        <div className="mt-2 flex items-center gap-1.5">
          {/* Tool selector */}
          <span className="text-[10px] text-slate-400 mr-1">工具</span>
          <button
            className={`rounded-md px-2 py-0.5 text-[10px] font-medium transition-colors ${
              tool === "draw"
                ? "bg-violet-600 text-white"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200"
            }`}
            onClick={() => { setTool("draw"); setIsClosed(false); }}
          >
            绘制
          </button>
          <button
            className={`rounded-md px-2 py-0.5 text-[10px] font-medium transition-colors ${
              tool === "select"
                ? "bg-violet-600 text-white"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200"
            }`}
            onClick={() => setTool("select")}
          >
            选择
          </button>

          <span className="text-slate-200 mx-1">|</span>

          {/* Draw mode selector */}
          <span className="text-[10px] text-slate-400 mr-1">模式</span>
          <button
            className={`rounded-md px-2 py-0.5 text-[10px] font-medium transition-colors ${
              drawMode === "orthogonal"
                ? "bg-violet-600 text-white"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200"
            }`}
            onClick={() => setDrawMode("orthogonal")}
          >
            正交
          </button>
          <button
            className={`rounded-md px-2 py-0.5 text-[10px] font-medium transition-colors ${
              drawMode === "free"
                ? "bg-violet-600 text-white"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200"
            }`}
            onClick={() => setDrawMode("free")}
          >
            自由
          </button>
        </div>

        {/* Mode hint */}
        <div className="mt-1 text-[10px] text-slate-400">
          {tool === "draw" && !isClosed && drawMode === "orthogonal" && "正交绘制：点击放置顶点，线段自动吸附为水平/垂直，靠近起点点击闭合"}
          {tool === "draw" && !isClosed && drawMode === "free" && "自由绘制：点击放置顶点，靠近起点点击闭合"}
          {tool === "draw" && isClosed && "多边形已闭合。点击「选择」工具可拖拽顶点调整"}
          {tool === "select" && "选择模式：拖拽顶点调整外轮廓"}
        </div>

        {/* SVG Canvas */}
        <div
          className="mt-2 rounded-lg border border-slate-200 bg-white"
          style={{ height: "calc(100% - 140px)", minHeight: "200px" }}
        >
          <svg
            ref={svgRef}
            className="h-full w-full"
            viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
            onClick={(e) => {
              if (!panStart && tool === "draw") addVertex(e);
            }}
            onWheel={handleWheel}
            onMouseDown={handleSvgMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={() => { handleMouseUp(); setMousePos(null); }}
            style={{ cursor: panStart ? "grabbing" : tool === "select" ? "default" : "crosshair" }}
          >
            {/* Grid */}
            {gridLines}

            {/* Axis labels */}
            {Array.from({ length: Math.ceil(vb.x + vb.w) + 1 }, (_, i) => i).filter(
              (i) => i >= Math.floor(vb.x) && i <= Math.ceil(vb.x + vb.w) && i % gridStep === 0
            ).map((i) => (
              <text key={`lx${i}`} x={i} y={vb.y + 0.3} fontSize="0.25" fill="#94a3b8" textAnchor="middle">{i}m</text>
            ))}

            {/* Outline polygon fill */}
            {vertices.length >= 3 && (
              <polygon
                points={polyPoints}
                fill="rgba(139,92,246,0.06)"
                stroke="none"
              />
            )}

            {/* Placed edges (solid) */}
            {vertices.length >= 2 && (
              <polyline
                points={polyPoints}
                fill="none"
                stroke="#7c3aed"
                strokeWidth="0.06"
              />
            )}

            {/* Closing edge when polygon is closed */}
            {isClosed && vertices.length >= 3 && (
              <line
                x1={vertices[vertices.length - 1].x}
                y1={vertices[vertices.length - 1].y}
                x2={vertices[0].x}
                y2={vertices[0].y}
                stroke="#7c3aed"
                strokeWidth="0.06"
              />
            )}

            {/* Preview line for draw mode */}
            {previewPoint && !isClosed && (
              <>
                <line
                  x1={vertices[vertices.length - 1].x}
                  y1={vertices[vertices.length - 1].y}
                  x2={previewPoint.x}
                  y2={previewPoint.y}
                  stroke="#c4b5fd"
                  strokeWidth="0.04"
                  strokeDasharray="0.1,0.06"
                />
                {/* Preview closing line to first vertex */}
                {vertices.length >= 2 && (
                  <line
                    x1={previewPoint.x}
                    y1={previewPoint.y}
                    x2={vertices[0].x}
                    y2={vertices[0].y}
                    stroke="#e2e8f0"
                    strokeWidth="0.03"
                    strokeDasharray="0.08,0.06"
                  />
                )}
                <circle cx={previewPoint.x} cy={previewPoint.y} r="0.12" fill="none" stroke="#c4b5fd" strokeWidth="0.04" />
              </>
            )}

            {/* Close indicator on first vertex */}
            {nearFirst && (
              <circle
                cx={vertices[0].x}
                cy={vertices[0].y}
                r="0.35"
                fill="rgba(139,92,246,0.15)"
                stroke="#7c3aed"
                strokeWidth="0.05"
              />
            )}

            {/* Vertices */}
            {vertices.map((v, i) => (
              <g key={i}>
                {/* Outer circle (hit area) */}
                <circle
                  cx={v.x} cy={v.y} r={VERTEX_HIT_RADIUS}
                  fill="transparent"
                  stroke="none"
                  style={{ cursor: tool === "select" ? "grab" : "crosshair" }}
                />
                {/* Visual circle */}
                <circle
                  cx={v.x} cy={v.y} r="0.18"
                  fill={dragIndex === i ? "#fbbf24" : "white"}
                  stroke={nearFirst && i === 0 ? "#7c3aed" : "#7c3aed"}
                  strokeWidth="0.05"
                  style={{ cursor: tool === "select" ? "grab" : "pointer" }}
                />
                <circle cx={v.x} cy={v.y} r="0.08" fill="#7c3aed" />
                <text
                  x={v.x + 0.25}
                  y={v.y - 0.2}
                  fontSize="0.2"
                  fill="#6d28d9"
                >
                  {`(${v.x},${v.y})`}
                </text>
              </g>
            ))}

            {/* Orthogonal right-angle marks */}
            {vertices.length >= 3 && drawMode === "orthogonal" &&
              vertices.map((v, i) => {
                const prev = vertices[(i - 1 + vertices.length) % vertices.length];
                const next = vertices[(i + 1) % vertices.length];
                const dx1 = v.x - prev.x;
                const dy1 = v.y - prev.y;
                const dx2 = next.x - v.x;
                const dy2 = next.y - v.y;
                const isOrtho1 = Math.abs(dx1) < 0.01 || Math.abs(dy1) < 0.01;
                const isOrtho2 = Math.abs(dx2) < 0.01 || Math.abs(dy2) < 0.01;
                if (!isOrtho1 || !isOrtho2) return null;
                const len1 = Math.sqrt(dx1 * dx1 + dy1 * dy1);
                const len2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);
                if (len1 < 0.01 || len2 < 0.01) return null;
                const markSize = 0.25;
                const ux1 = dx1 / len1 * markSize;
                const uy1 = dy1 / len1 * markSize;
                const ux2 = dx2 / len2 * markSize;
                const uy2 = dy2 / len2 * markSize;
                return (
                  <polyline
                    key={`rm${i}`}
                    points={`${v.x - ux1},${v.y - uy1} ${v.x - ux1 + ux2},${v.y - uy1 + uy2} ${v.x + ux2},${v.y + uy2}`}
                    fill="none"
                    stroke="#c4b5fd"
                    strokeWidth="0.03"
                  />
                );
              })
            }

            {/* Dimension labels on edges */}
            {vertices.length >= 2 && vertices.map((v, i) => {
              const next = vertices[(i + 1) % vertices.length];
              const isClosingEdge = i === vertices.length - 1;
              if (isClosingEdge && !isClosed && vertices.length < 3) return null;
              if (isClosingEdge && !isClosed) return null;
              const mx = (v.x + next.x) / 2;
              const my = (v.y + next.y) / 2;
              const d = dist(v, next);
              const isHorizontal = Math.abs(next.y - v.y) < 0.01;
              const isVertical = Math.abs(next.x - v.x) < 0.01;
              const labelOffsetX = isVertical ? 0.35 : 0;
              const labelOffsetY = isHorizontal ? -0.25 : 0;
              return (
                <text
                  key={`d${i}`}
                  x={mx + labelOffsetX}
                  y={my + labelOffsetY}
                  fontSize="0.22"
                  fill="#7c3aed"
                  textAnchor="middle"
                  fontWeight="500"
                >
                  {d.toFixed(2)}m
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
          {isClosed && " · 已闭合"}
          <span className="ml-2 text-[10px]">
            滚轮缩放 · Shift+拖拽平移 · 网格吸附 {GRID_SNAP}m
          </span>
        </div>
        <div className="flex gap-1.5">
          <button className="fpw-icon-btn bg-slate-100 text-slate-600 hover:bg-slate-200" onClick={resetView} title="重置视图">
            <Icon name="refresh" size={11} />
          </button>
          <button className="fpw-icon-btn bg-slate-100 text-slate-600 hover:bg-slate-200" onClick={removeLastVertex} title="撤销" disabled={isClosed && vertices.length <= 3}>
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
  return { x: view.cx - halfSpan, y: view.cy - halfSpan, w, h };
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
