import os
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.orchestrator.workflow import Orchestrator
from app.repositories.session_repo import create_session_repository
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    CreateSessionResponse,
    RegenerateDraftRequest,
    RegeneratePlanRequest,
    ShutdownRequest,
    ShutdownResponse,
)
from app.schemas.layout import SiteOutline
from app.services.drawer_service import DrawerService
from app.services.layout_service import LayoutService
from app.services.planner_service import PlannerService
from app.services.requirement_memory import align_memory_with_outline

router = APIRouter(prefix="/api/v1")

repo = create_session_repository()
orchestrator = Orchestrator(
    repo=repo,
    planner_service=PlannerService(),
    drawer_service=DrawerService(),
    layout_service=LayoutService(),
)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session() -> CreateSessionResponse:
    session = repo.create()
    return CreateSessionResponse(session_id=session.session_id)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    """Remove session and all chat history from persistence."""
    if not repo.delete(session_id):
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"status": "ok", "session_id": session_id, "cleared": True}


@router.post("/sessions/{session_id}/end")
def end_session(session_id: str) -> dict:
    """Idempotent end: delete session if present (for page close / beacon)."""
    cleared = repo.delete(session_id)
    return {"status": "ok", "session_id": session_id, "cleared": cleared}


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    try:
        session = repo.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session.model_dump()


@router.post("/sessions/{session_id}/outline")
def save_session_outline(session_id: str, body: SiteOutline) -> dict:
    try:
        session = repo.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.site_outline = body
    merged = dict(session.collected_requirements or {})
    merged, notices = align_memory_with_outline(merged, body)
    session.collected_requirements = merged
    repo.save(session)
    return {"status": "ok", "outline": body.model_dump(), "notices": notices}


@router.get("/sessions/{session_id}/outline")
def get_session_outline(session_id: str) -> dict:
    try:
        session = repo.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if session.site_outline is None:
        return {"status": "no_outline"}
    return {"status": "ok", "outline": session.site_outline.model_dump()}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        return orchestrator.handle_chat(
            session_id=req.session_id,
            user_message=req.user_message,
            draw_method=req.draw_method,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/plan/regenerate", response_model=ChatResponse)
def regenerate_plan(req: RegeneratePlanRequest) -> ChatResponse:
    try:
        return orchestrator.regenerate_plan(
            session_id=req.session_id,
            modification_request=req.modification_request,
            draw_method=req.draw_method,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/draft/regenerate", response_model=ChatResponse)
def regenerate_draft(req: RegenerateDraftRequest) -> ChatResponse:
    try:
        return orchestrator.regenerate_draft(session_id=req.session_id, draw_method=req.draw_method)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/system/shutdown", response_model=ShutdownResponse)
def shutdown_application(req: ShutdownRequest | None = None) -> ShutdownResponse:
    session_cleared = False
    if req and req.session_id:
        session_cleared = repo.delete(req.session_id)

    flag_path = os.getenv("FLOORPLAN_SHUTDOWN_FILE", "").strip()
    if flag_path:
        Path(flag_path).write_text(str(time.time()), encoding="utf-8")

    def _exit_process() -> None:
        time.sleep(0.6)
        os._exit(0)

    threading.Thread(target=_exit_process, daemon=True).start()
    msg = "正在关闭 FloorPlanWeaver 服务…"
    if session_cleared:
        msg += " 已清理当前会话对话记录。"
    return ShutdownResponse(
        status="shutting_down",
        message=msg,
        session_cleared=session_cleared,
    )
