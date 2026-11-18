from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", protected_namespaces=("settings_",))

    app_name: str = "academic-events"
    database_url: str = "postgresql+psycopg://academic:academic_pass@localhost:5432/academic_events"
    seed_on_startup: bool = False

    jwt_secret: str = "dev-secret"
    jwt_expires_minutes: int = 12 * 60

    # Provedor de LLM (Gemini). Sem chave, os agentes ficam em modo degradado.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_model_light: str = "gemini-3.5-flash-lite"
    gemini_fallback_models: str = "gemini-3.1-flash-lite,gemini-flash-lite-latest"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    model_timeout_seconds: float = 20.0
    model_max_retries: int = 2

    # Limites padrão das execuções de agentes
    agent_max_steps: int = 8
    agent_max_tokens: int = 60_000
    agent_run_timeout_seconds: float = 120.0
    tool_timeout_seconds: float = 5.0

    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.gemini_fallback_models.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
