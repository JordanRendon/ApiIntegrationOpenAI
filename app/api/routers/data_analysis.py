from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.dependencies import get_openai_service
from app.services.openai_service import OpenAIService

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/analyze")
async def analyze_file(
    file: UploadFile = File(...),
    prompt: str = Form(...),
    openai_service: OpenAIService = Depends(get_openai_service),
):
    """
    Endpoint para analizar archivos (PDF, JPG, JPEG, PNG) con OpenAI.
    """
    allowed_extensions = [".pdf", ".jpg", ".jpeg", ".png"]
    file_ext = next((ext for ext in allowed_extensions if file.filename.lower().endswith(ext)), None)

    if not file_ext:
        return {
            "error": True,
            "message": "File must be PDF, JPG, JPEG, or PNG",
            "tokens_input": 0,
            "tokens_output": 0,
            "data": {},
        }

    try:
        if file_ext == ".pdf":
            result, tokens_input, tokens_output = await openai_service.process_pdf(file.file, prompt)
        else:
            result, tokens_input, tokens_output = await openai_service.process_image(file.file, prompt)

        return {
            "error": False,
            "message": "",
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "data": result,
        }
    except Exception as exc:  # pragma: no cover - passthrough for API response parity
        return {
            "error": True,
            "message": str(exc),
            "tokens_input": 0,
            "tokens_output": 0,
            "data": {},
        }

