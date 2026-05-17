import os

from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    app_name: str = "FloorPlanWeaver API"
    app_version: str = "0.1.0"
    llm_provider: str = "mock"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_mock_mode: bool = True
    planner_use_llm: bool = False
    drawer_use_llm: bool = False
    drawer_fallback_to_rule: bool = False
    planner_model: str = "planner-model"
    drawer_model: str = "drawer-model"
    llm_timeout_seconds: int = 45
    llm_max_retries: int = 2

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", "FloorPlanWeaver API"),
            app_version=os.getenv("APP_VERSION", "0.1.0"),
            llm_provider=os.getenv("LLM_PROVIDER", "mock"),
            llm_api_base=os.getenv("LLM_API_BASE", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_mock_mode=os.getenv("LLM_MOCK_MODE", "true").lower() == "true",
            planner_use_llm=os.getenv("PLANNER_USE_LLM", "false").lower() == "true",
            drawer_use_llm=os.getenv("DRAWER_USE_LLM", "false").lower() == "true",
            drawer_fallback_to_rule=os.getenv("DRAWER_FALLBACK_TO_RULE", "false").lower()
            == "true",
            planner_model=os.getenv("PLANNER_MODEL", "planner-model"),
            drawer_model=os.getenv("DRAWER_MODEL", "drawer-model"),
            llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
            llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        )


settings = Settings.from_env()
