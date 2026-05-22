import type {
  ApiLayoutOutput,
  LayoutOutput,
  LayoutRoom,
  Point2D,
  SiteOutline,
} from "./types";

type ApiLayoutRoom = NonNullable<
  NonNullable<ApiLayoutOutput["layout"]>["rooms"]
>[number];

function normalizeRoom(raw: ApiLayoutRoom): LayoutRoom {
  return {
    room_id: raw.room_id ?? raw.id ?? "",
    name: raw.name ?? "",
    room_type: raw.room_type ?? raw.type ?? "",
    pts: raw.pts ?? raw.polygon ?? [],
    area_sqm: raw.area_sqm ?? 0,
    shape_kind: raw.shape_kind,
  };
}

function buildOutline(
  vertices: Point2D[],
  entranceEdge?: number[],
  canvas?: Record<string, number>,
): SiteOutline {
  const xs = vertices.map((v) => v.x);
  const ys = vertices.map((v) => v.y);
  const width =
    canvas?.width ?? (xs.length ? Math.max(...xs) - Math.min(...xs) : 0);
  const height =
    canvas?.height ?? (ys.length ? Math.max(...ys) - Math.min(...ys) : 0);
  return {
    vertices,
    entrance_edge: entranceEdge ?? [0, 1],
    total_area_sqm: canvas?.total_area_sqm ?? width * height,
    bounding_box: { width, height },
    unit: "meter",
  };
}

/** Map backend LayoutOutput (nested draft) to the viewer's flat LayoutOutput. */
export function normalizeLayout(raw: unknown): LayoutOutput | null {
  if (!raw || typeof raw !== "object") return null;
  const api = raw as ApiLayoutOutput;

  if (Array.isArray(api.rooms)) {
    const rooms = api.rooms.map((r) => normalizeRoom(r as ApiLayoutRoom));
    if (!rooms.length && !api.svg_base64) return null;
    return {
      rooms,
      outline: api.outline ?? buildOutline([]),
      compile_method: api.compile_method ?? "legacy",
      svg_base64: api.svg_base64,
      notes: api.notes,
    };
  }

  const draft = api.layout;
  if (!draft) return null;

  const rooms = (draft.rooms ?? []).map(normalizeRoom);
  const vertices = draft.outline_vertices ?? [];
  if (!rooms.length && !api.svg_base64) return null;

  return {
    rooms,
    outline: buildOutline(vertices, draft.entrance_edge, draft.canvas),
    compile_method:
      draft.compile_method ?? api.render_source ?? "legacy",
    svg_base64: api.svg_base64,
    notes: api.notes,
  };
}
