"""Common dependency providers."""

from functools import lru_cache

from app.services.openai_service import OpenAIService


@lru_cache
def get_openai_service() -> OpenAIService:
    """
    Retorna una instancia singleton del OpenAIService para reutilizar conexiones.
    """
    return OpenAIService()

