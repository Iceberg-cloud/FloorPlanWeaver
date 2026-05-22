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
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  if (pointInRing(cx, cy, ring)) return { x: cx, y: cy };
  let sx = 0;
  let sy = 0;
  for (const p of ring) {
    sx += p.x;
    sy += p.y;
  }
  return { x: sx / ring.length, y: sy / ring.length };
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
