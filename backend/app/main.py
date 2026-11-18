import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.agentic.api.router import router as agents_router
from app.core import database
from app.core.config import get_settings
from app.core.correlation import CorrelationMiddleware
from app.core.errors import DomainError, domain_error_handler
from app.knowledge.router import router as knowledge_router
from app.modules.activity.router import router as activity_router
from app.modules.approvals.router import router as approvals_router
from app.modules.auth.router import router as auth_router
from app.modules.events.router import router as events_router
from app.modules.notifications.router import router as notifications_router
from app.modules.tickets.router import router as tickets_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()

app = FastAPI(
    title="academic-events API",
    version="0.1.0",
    description="Plataforma de eventos acadêmicos com agentes de IA: assistente do participante, agente de operações e revisor.",
)
app.add_middleware(CorrelationMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Correlation-Id"])
app.add_exception_handler(DomainError, domain_error_handler)

for r in (agents_router, auth_router, events_router, tickets_router, approvals_router, notifications_router, activity_router, knowledge_router):
    app.include_router(r)


@app.on_event("startup")
def startup() -> None:
    database.create_all()
    if settings.seed_on_startup:
        from app.seed.seed import seed

        with database.session_factory()() as db:
            logging.getLogger("academic_events").info("[SEED] %s", seed(db))


@app.get("/health", tags=["health"])
def health():
    with database.engine().connect() as conn:
        conn.execute(text("select 1"))
    from app.agentic.providers import get_model

    model = get_model()
    breakers = {name: b.state for name, b in getattr(model, "breakers", {}).items()}
    return {"status": "ok", "llm": {"provider": model.name, "configured": bool(settings.gemini_api_key), "circuits": breakers}}
