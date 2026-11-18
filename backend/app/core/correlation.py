"""X-Correlation-Id: liga requisição, execução de agente, tools e auditoria (herdado do events-tickets-ms, D7)."""

import contextvars
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")
logger = logging.getLogger("academic_events")


def current_correlation_id() -> str:
    return correlation_id_var.get()


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        cid = request.headers.get("X-Correlation-Id") or f"req-{uuid.uuid4().hex[:12]}"
        token = correlation_id_var.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers["X-Correlation-Id"] = cid
        logger.info("[HTTP] %s %s -> %s (%.0f ms) cid=%s", request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000, cid)
        return response
