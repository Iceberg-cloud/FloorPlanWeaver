import logging
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"
ENV_EXAMPLE_FILE = BACKEND_DIR / ".env.example"


def _ensure_env_file() -> Path | None:
    if ENV_FILE.exists():
        return ENV_FILE
    if not ENV_EXAMPLE_FILE.exists():
        return None
    shutil.copy2(ENV_EXAMPLE_FILE, ENV_FILE)
    logger.warning("已自动从 .env.example 创建 backend/.env，请按需修改其中的密钥与模型名。")
    return ENV_FILE


def load_env() -> None:
    env_path = _ensure_env_file()
    if env_path is not None:
        load_dotenv(env_path, override=True)
        return
    if ENV_EXAMPLE_FILE.exists():
        load_dotenv(ENV_EXAMPLE_FILE, override=True)
        logger.warning(
            "backend/.env 不存在，已临时加载 .env.example。"
            "建议复制为 .env：copy backend\\.env.example backend\\.env"
        )


def _env_str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_bool(key: str, default: str = "false") -> bool:
    return _env_str(key, default).lower() == "true"


load_env()


class Settings(BaseModel):
    app_name: str = "FloorPlanWeaver API"
    app_version: str = "0.1.0"
    llm_provider: str = "mock"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_mock_mode: bool = True
    planner_use_llm: bool = False
    drawer_use_llm: bool = False
    drawer_fallback_to_rule: bool = True
    default_draw_mode: str = "layout"
    planner_model: str = "planner-model"
    drawer_model: str = "drawer-model"
    layout_model: str = ""
    llm_timeout_seconds: int = 120
    layout_timeout_seconds: int = 120
    llm_hard_timeout_seconds: int = 120
    llm_max_retries: int = 2
    layout_llm_max_retries: int = 1
    layout_use_grid_compiler: bool = True
    session_store: str = "sqlite"
    session_db_path: Path = BACKEND_DIR / "data" / "sessions.db"
    planner_max_history_turns: int = 8
    planner_max_ask_rounds: int = 1

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=_env_str("APP_NAME", "FloorPlanWeaver API"),
            app_version=_env_str("APP_VERSION", "0.1.0"),
            llm_provider=_env_str("LLM_PROVIDER", "mock"),
            llm_api_base=_env_str("LLM_API_BASE", ""),
            llm_api_key=_env_str("LLM_API_KEY", ""),
            llm_mock_mode=_env_bool("LLM_MOCK_MODE", "true"),
            planner_use_llm=_env_bool("PLANNER_USE_LLM", "false"),
            drawer_use_llm=_env_bool("DRAWER_USE_LLM", "false"),
            drawer_fallback_to_rule=_env_bool("DRAWER_FALLBACK_TO_RULE", "true"),
            default_draw_mode=_env_str("DEFAULT_DRAW_MODE", "layout"),
            planner_model=_env_str("PLANNER_MODEL", "planner-model"),
            drawer_model=_env_str("DRAWER_MODEL", "drawer-model"),
            layout_model=_env_str("LAYOUT_MODEL", ""),
            llm_timeout_seconds=min(
                int(_env_str("LLM_TIMEOUT_SECONDS", "120")),
                int(_env_str("LLM_HARD_TIMEOUT_SECONDS", "120")),
            ),
            layout_timeout_seconds=min(
                int(_env_str("LAYOUT_TIMEOUT_SECONDS", "120")),
                int(_env_str("LLM_HARD_TIMEOUT_SECONDS", "120")),
            ),
            llm_hard_timeout_seconds=int(_env_str("LLM_HARD_TIMEOUT_SECONDS", "120")),
            llm_max_retries=int(_env_str("LLM_MAX_RETRIES", "2")),
            layout_llm_max_retries=int(_env_str("LAYOUT_LLM_MAX_RETRIES", "1")),
            layout_use_grid_compiler=_env_bool("LAYOUT_USE_GRID_COMPILER", "true"),
            session_store=_env_str("SESSION_STORE", "sqlite").lower(),
            session_db_path=Path(_env_str("SESSION_DB_PATH", str(BACKEND_DIR / "data" / "sessions.db"))),
            planner_max_history_turns=int(_env_str("PLANNER_MAX_HISTORY_TURNS", "8")),
            planner_max_ask_rounds=int(_env_str("PLANNER_MAX_ASK_ROUNDS", "1")),
        )

    @property
    def layout_model_name(self) -> str:
        return self.layout_model or self.planner_model

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_base and self.llm_api_key)


settings = Settings.from_env()
