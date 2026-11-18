"""Composição dos adapters (ponto único onde o provedor concreto é escolhido)."""

from functools import lru_cache

from app.agentic.adapters.gemini import GeminiAdapter
from app.agentic.ports.model import ModelPort

_override: ModelPort | None = None


@lru_cache
def _gemini() -> GeminiAdapter:
    return GeminiAdapter()


def get_model() -> ModelPort:
    return _override or _gemini()


def set_model_override(model: ModelPort | None) -> None:
    """Testes e evals trocam o modelo (ex.: FakeModel) sem tocar no domínio."""
    global _override
    _override = model
