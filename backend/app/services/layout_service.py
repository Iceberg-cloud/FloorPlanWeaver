"""LayoutService: semantic LLM → compiler → post-process → SVG."""
from __future__ import annotations
from app.agents.layout_agent import build_layout_prompt, parse_semantic_json
from app.renderers.svg_renderer import render_layout_svg
from app.schemas.layout import LayoutDraft, LayoutOutput, LayoutValidationResult, SiteOutline
from app.schemas.planner import PlannerFinalPlan
from app.schemas.semantic_layout import SemanticLayoutPlan
from app.services.default_semantic_layout import build_default_semantic_plan
from app.services.layout_compiler import compile_semantic_layout
from app.services.layout_postprocess import normalize_rooms_to_rects, postprocess_layout
from app.services.layout_validator import validate_layout
from app.services.semantic_validator import validate_semantic_plan
from app.core.config import settings
from app.services.llm_client import LLMClient


class LayoutService:
    def __init__(self):
        self.llm_client = LLMClient()

    def generate(self, plan, outline):
        if not settings.planner_use_llm or settings.llm_mock_mode:
            return self._compile_result(plan, outline, build_default_semantic_plan(plan),
                                        prompt="default-semantic", llm_enabled=False,
                                        llm_attempted=False, llm_succeeded=False,
                                        fallback_to_rule=True, error=None)
        semantic, prompt, llm_succeeded, error = None, None, False, None
        try:
            semantic, prompt = self._call_semantic_llm(plan, outline, [])
            llm_succeeded = True
        except Exception as exc:
            error = str(exc)
        if semantic is None:
            semantic = build_default_semantic_plan(plan)
            return self._compile_result(plan, outline, semantic, prompt="default-semantic",
                                        llm_enabled=True, llm_attempted=True,
                                        llm_succeeded=False, fallback_to_rule=True, error=error)
        return self._compile_result(plan, outline, semantic, prompt=prompt,
                                    llm_enabled=True, llm_attempted=True,
                                    llm_succeeded=True, fallback_to_rule=False, error=None)

    def _call_semantic_llm(self, plan, outline, last_errors):
        from app.services.layout_geometry import bbox_of_polygon
        poly = [(v.x, v.y) for v in outline.vertices]
        min_x, min_y, max_x, max_y = bbox_of_polygon(poly)
        prompt = build_layout_prompt(plan, outline.vertices, outline.entrance_edge, outline.total_area_sqm,
                                     validation_errors=last_errors if last_errors else None)
        data = self.llm_client.generate_json(system_prompt=SEMANTIC_LAYOUT_SYSTEM_PROMPT,
                                              messages=[{"role": "user", "content": prompt}],
                                              model=settings.layout_model_name,
                                              timeout_seconds=settings.layout_timeout_seconds,
                                              max_retries=settings.layout_llm_max_retries)
        return parse_semantic_json(data), prompt

    def _compile_result(self, plan, outline, semantic, *, prompt, llm_enabled, llm_attempted,
                        llm_succeeded, fallback_to_rule, error):
        assert outline is not None
        layout, compile_notes = compile_semantic_layout(semantic, plan, outline)
        layout, extra = self._postprocess(layout, outline, plan)
        extra = list(compile_notes) + list(extra)
        validation = validate_layout(layout, outline, plan)
        svg = render_layout_svg(layout)
        import base64
        svg_b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        render_source = "layout_rule" if fallback_to_rule else "layout_semantic"
        from app.services.layout_metrics import compute_layout_area_metrics

        metrics = compute_layout_area_metrics(layout, outline)
        extra.append(metrics.summary_line())
        return LayoutOutput(
            layout=layout,
            svg_base64=svg_b64,
            validation=validation,
            render_source=render_source,
            notes=extra,
            area_coverage_ratio=metrics.area_coverage_ratio,
            planned_area_sqm=metrics.planned_area_sqm,
            outline_area_sqm=metrics.outline_area_sqm,
        )

    def _postprocess(self, layout, outline, plan):
        # Grid search compiler already guarantees geometric correctness:
        # rooms are inside outline, no gaps, no overlaps, full coverage.
        # Rect-based post-processing (shrink_rect_into_polygon, de-overlap)
        # would destroy the precise grid-aligned coordinates.
        if layout.compile_method == "grid_search":
            from app.services.layout_metrics import compute_layout_area_metrics
            return layout, []
        layout = normalize_rooms_to_rects(layout)
        return postprocess_layout(layout, outline, plan)
