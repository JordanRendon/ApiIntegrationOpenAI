"""Router registrations for Medicar AI API."""

from fastapi import APIRouter

from . import catalog, data_analysis, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(data_analysis.router)
api_router.include_router(catalog.router)

__all__ = ["api_router"]

