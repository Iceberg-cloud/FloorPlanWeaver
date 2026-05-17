from fastapi import APIRouter, HTTPException

from app.orchestrator.workflow import Orchestrator
from app.repositories.session_repo import InMemorySessionRepository
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    CreateSessionResponse,
    RegenerateDraftRequest,
    RegeneratePlanRequest,
)
from app.services.drawer_service import DrawerService
from app.services.planner_service import PlannerService

router = APIRouter(prefix="/api/v1")

repo = InMemorySessionRepository()
orchestrator = Orchestrator(
    repo=repo,
    planner_service=PlannerService(),
    drawer_service=DrawerService(),
)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session() -> CreateSessionResponse:
    session = repo.create()
    return CreateSessionResponse(session_id=session.session_id)


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    try:
        session = repo.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return session.model_dump()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        return orchestrator.handle_chat(session_id=req.session_id, user_message=req.user_message)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/plan/regenerate", response_model=ChatResponse)
def regenerate_plan(req: RegeneratePlanRequest) -> ChatResponse:
    try:
        return orchestrator.regenerate_plan(
            session_id=req.session_id, modification_request=req.modification_request
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/draft/regenerate", response_model=ChatResponse)
def regenerate_draft(req: RegenerateDraftRequest) -> ChatResponse:
    try:
        return orchestrator.regenerate_draft(session_id=req.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
