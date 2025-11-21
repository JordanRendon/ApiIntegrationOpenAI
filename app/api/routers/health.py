from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """
    Health check endpoint to verify service status.
    """
    return {"status": "ok"}

