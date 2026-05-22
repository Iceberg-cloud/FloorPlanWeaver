export type Point2D = { x: number; y: number };

export type SiteOutline = {
  vertices: Point2D[];
  entrance_edge: number[];
  total_area_sqm: number;
  bounding_box: { width: number; height: number };
  unit: string;
};

export type PlannerAskForMore = {
  agent_state: "ASK_FOR_MORE";
  missing_fields: string[];
  follow_up_questions: string[];
  collected_snapshot: Record<string, unknown>;
};

export type PlannerFinalPlan = {
  agent_state: "FINAL_PLAN";
  project_profile: Record<string, unknown>;
  design_goals: string[];
  space_program: Array<Record<string, unknown>>;
  adjacency_graph: Array<Record<string, unknown>>;
  circulation: Record<string, unknown>;
  openings_strategy: Record<string, unknown>;
  orientation_daylighting: Record<string, unknown>;
  zoning: Record<string, unknown>;
  drawing_brief: string;
  change_summary: string[];
  owner_summary?: string;
};

export type LayoutRoom = {
  room_id: string;
  name: string;
  room_type: string;
  pts: Point2D[];
  area_sqm: number;
  shape_kind?: string;
  floor_level?: number;
};

export type LayoutOutput = {
  rooms: LayoutRoom[];
  outline: SiteOutline;
  compile_method: string;
  svg_base64?: string | null;
  notes?: string[];
};

/** Nested layout object returned by the backend API. */
export type ApiLayoutOutput = {
  drawing_state?: string;
  render_source?: string;
  layout?: {
    rooms?: Array<{
      id?: string;
      room_id?: string;
      name?: string;
      type?: string;
      room_type?: string;
      polygon?: Point2D[];
      pts?: Point2D[];
      area_sqm?: number;
      shape_kind?: string;
    }>;
    outline_vertices?: Point2D[];
    entrance_edge?: number[];
    compile_method?: string;
    canvas?: Record<string, number>;
  };
  rooms?: LayoutRoom[];
  outline?: SiteOutline;
  compile_method?: string;
  svg_base64?: string | null;
  notes?: string[];
};

export type DrawerDraft = {
  drawing_state: "IMAGE_READY";
  image_url?: string | null;
  image_base64?: string | null;
  image_mime_type: string;
  image_prompt: string;
  model: string;
  size: string;
  validation: { hard_constraints_passed: boolean; notes: string[] };
};

export type ChatResponse = {
  status: "collecting" | "completed" | "draft_failed";
  planner: PlannerAskForMore | PlannerFinalPlan;
  drawer?: DrawerDraft | null;
  layout?: ApiLayoutOutput | null;
  area_coverage_ratio?: number | null;
  planned_area_sqm?: number | null;
  outline_area_sqm?: number | null;
  progress: {
    collected_fields: string[];
    missing_fields: string[];
  };
  runtime: {
    planner: {
      llm_enabled: boolean;
      llm_attempted: boolean;
      llm_succeeded: boolean;
      fallback_to_rule: boolean;
      error?: string | null;
    };
    drawer?: {
      llm_enabled: boolean;
      llm_attempted: boolean;
      llm_succeeded: boolean;
      fallback_to_rule: boolean;
      error?: string | null;
    } | null;
    layout?: {
      llm_enabled: boolean;
      llm_attempted: boolean;
      llm_succeeded: boolean;
      fallback_to_rule: boolean;
      error?: string | null;
    } | null;
  };
};
