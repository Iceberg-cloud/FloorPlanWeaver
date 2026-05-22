import type { DrawMethod } from "../components/ActionBar";

export type PipelineOperation = "chat" | "regenerate_plan" | "regenerate_draft";

export type PipelineStageId =
  | "planner"
  | "layout_semantic"
  | "layout_compile"
  | "layout_post"
  | "drawer";

export type PipelineStage = {
  id: PipelineStageId;
  agent: string;
  label: string;
  hint: string;
  icon: "brain" | "layout" | "grid" | "sparkles" | "image";
  durationMs: number;
};

const STAGE_PLANNER: PipelineStage = {
  id: "planner",
  agent: "规划师",
  label: "规划师思考中",
  hint: "解析需求、补全信息或生成空间方案",
  icon: "brain",
  durationMs: 2800,
};

const STAGE_LAYOUT_SEMANTIC: PipelineStage = {
  id: "layout_semantic",
  agent: "布局顾问",
  label: "布局顾问分析中",
  hint: "LLM 给出房间大致位置与相对尺寸",
  icon: "sparkles",
  durationMs: 2400,
};

const STAGE_LAYOUT_COMPILE: PipelineStage = {
  id: "layout_compile",
  agent: "布局工程师",
  label: "布局工程师编译中",
  hint: "网格布置、邻接吸附并占满轮廓",
  icon: "grid",
  durationMs: 2200,
};

const STAGE_LAYOUT_POST: PipelineStage = {
  id: "layout_post",
  agent: "布局工程师",
  label: "布局优化中",
  hint: "裁剪重叠、对齐邻接边并填满空隙",
  icon: "layout",
  durationMs: 1800,
};

const STAGE_DRAWER: PipelineStage = {
  id: "drawer",
  agent: "设计师",
  label: "设计师绘图中",
  hint: "多模态模型生成户型效果图",
  icon: "image",
  durationMs: 3200,
};

function layoutStages(): PipelineStage[] {
  return [STAGE_LAYOUT_SEMANTIC, STAGE_LAYOUT_COMPILE, STAGE_LAYOUT_POST];
}

function drawerStages(): PipelineStage[] {
  return [STAGE_DRAWER];
}

/** Stages shown while waiting for a blocking API call (simulated progression). */
export function getPipelineStages(
  operation: PipelineOperation,
  drawMethod: DrawMethod,
): PipelineStage[] {
  switch (operation) {
    case "regenerate_plan":
      return [STAGE_PLANNER];
    case "regenerate_draft": {
      const stages: PipelineStage[] = [];
      if (drawMethod === "vector" || drawMethod === "both") {
        stages.push(...layoutStages());
      }
      if (drawMethod === "multimodal" || drawMethod === "both") {
        stages.push(...drawerStages());
      }
      return stages.length ? stages : [STAGE_PLANNER];
    }
    case "chat":
    default: {
      const stages: PipelineStage[] = [STAGE_PLANNER];
      if (drawMethod === "vector" || drawMethod === "both") {
        stages.push(...layoutStages());
      }
      if (drawMethod === "multimodal" || drawMethod === "both") {
        stages.push(...drawerStages());
      }
      return stages;
    }
  }
}

export function stageAtIndex(stages: PipelineStage[], index: number): PipelineStage | null {
  if (!stages.length) return null;
  return stages[Math.min(Math.max(0, index), stages.length - 1)];
}
