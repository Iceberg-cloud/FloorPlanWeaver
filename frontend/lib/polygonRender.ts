import type { Point2D } from "./types";

const EPS = 1e-6;

/** Remove duplicate/collinear vertices so SVG fills do not self-intersect. */
export function normalizePolygonRing(pts: Point2D[]): Point2D[] {
  if (pts.length < 3) return pts;
  const deduped: Point2D[] = [];
  for (const p of pts) {
    const last = deduped[deduped.length - 1];
    if (!last || Math.abs(last.x - p.x) > EPS || Math.abs(last.y - p.y) > EPS) {
      deduped.push(p);
    }
  }
  if (deduped.length >= 2) {
    const first = deduped[0];
    const last = deduped[deduped.length - 1];
    if (Math.abs(first.x - last.x) < EPS && Math.abs(first.y - last.y) < EPS) {
      deduped.pop();
    }
  }
  if (deduped.length < 3) return deduped;

  const out: Point2D[] = [];
  const n = deduped.length;
  for (let i = 0; i < n; i++) {
    const prev = deduped[(i - 1 + n) % n];
    const cur = deduped[i];
    const next = deduped[(i + 1) % n];
    const v1x = cur.x - prev.x;
    const v1y = cur.y - prev.y;
    const v2x = next.x - cur.x;
    const v2y = next.y - cur.y;
    const cross = v1x * v2y - v1y * v2x;
    if (Math.abs(cross) > EPS) out.push(cur);
  }
  return out.length >= 3 ? out : deduped;
}

/** Label anchor inside L/T polygons (bbox center can fall outside). */
export function polygonLabelCenter(pts: Point2D[]): { x: number; y: number } {
  if (!pts.length) return { x: 0, y: 0 };
  const ring = normalizePolygonRing(pts);
  const xs = ring.map((p) => p.x);
  const ys = ring.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  if (pointInRing(cx, cy, ring)) return { x: cx, y: cy };

  let bestX = cx;
  let bestY = cy;
  let bestDist = -1;
  const steps = 5;
  for (let si = 0; si < steps; si++) {
    for (let sj = 0; sj < steps; sj++) {
      const tx = minX + ((si + 0.5) / steps) * (maxX - minX);
      const ty = minY + ((sj + 0.5) / steps) * (maxY - minY);
      if (!pointInRing(tx, ty, ring)) continue;
      const dist = Math.min(tx - minX, maxX - tx, ty - minY, maxY - ty);
      if (dist > bestDist) {
        bestDist = dist;
        bestX = tx;
        bestY = ty;
      }
    }
  }
  if (bestDist >= 0) return { x: bestX, y: bestY };

  let sx = 0;
  let sy = 0;
  for (const p of ring) {
    sx += p.x;
    sy += p.y;
  }
  return { x: sx / ring.length, y: sy / ring.length };
}

/** Font sizes in SVG user units (meters), scaled from room bbox for readable Chinese labels.
 *
 * Ensures text fits inside the room bbox for all room types, especially narrow
 * rooms like balconies and small bathrooms where Chinese characters could be clipped.
 */
export function labelFontSizesFromBbox(pts: Point2D[]): {
  nameFs: number;
  areaFs: number;
  showArea: boolean;
  strokeW: number;
} {
  if (pts.length < 3) {
    return { nameFs: 0.28, areaFs: 0.2, showArea: false, strokeW: 0.05 };
  }
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const w = Math.max(0.35, Math.max(...xs) - Math.min(...xs));
  const h = Math.max(0.35, Math.max(...ys) - Math.min(...ys));
  const short = Math.min(w, h);
  const long = Math.max(w, h);

  // CJK characters are roughly square; for 2-4 char names we need short side
  // to accommodate at least 1 line of text. Typical Chinese room name is 2-3 chars.
  // At 1 char height ≈ nameFs, width ≈ nameFs too. For 3 chars we need ~3*nameFs width.
  // So nameFs ≤ short * 0.9 (leave margin) AND nameFs ≤ long / 4 (3 chars + margin).
  const maxFsByShort = short * 0.42;
  const maxFsByLong = long / 4.0;
  let nameFs = Math.min(0.58, maxFsByShort, maxFsByLong);
  nameFs = Math.max(0.18, nameFs);
  const areaFs = Math.max(0.15, nameFs * 0.68);
  // Only show area when the room is large enough that text won't overlap
  const showArea = short >= 1.1 && long >= 1.6 && nameFs >= 0.22;
  const strokeW = Math.min(0.08, Math.max(0.025, short * 0.05));
  return { nameFs, areaFs, showArea, strokeW };
}

export function roomBbox(pts: Point2D[]): { minX: number; minY: number; maxX: number; maxY: number } {
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  };
}

function pointInRing(px: number, py: number, ring: Point2D[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i].x;
    const yi = ring[i].y;
    const xj = ring[j].x;
    const yj = ring[j].y;
    const hit = (yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi + EPS) + xi;
    if (hit) inside = !inside;
  }
  return inside;
}
