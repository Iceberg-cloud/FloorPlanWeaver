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
  drawer?: DrawerDraft;
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
  };
};
