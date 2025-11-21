from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.dependencies import get_openai_service
from app.services.openai_service import OpenAIService

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.post("/analyze")
async def analyze_catalog_search(
    file: UploadFile = File(...),
    search: str = Form(...),
    prompt: str = Form(""),
    max_alternatives: int = Form(None),
    use_vectors: bool = Query(True, description="Usar Vector Search para máxima eficiencia"),
    openai_service: OpenAIService = Depends(get_openai_service),
):
    """
    Analiza términos de búsqueda contra un catálogo .txt utilizando OpenAI GPT-4o-mini.
    """
    print("=" * 80)
    print(f"[CONTROLLER] Recibido request en /catalog/analyze (vectors={use_vectors})")
    print(f"[CONTROLLER] Archivo: {file.filename}")
    print(f"[CONTROLLER] Search: {search}")
    print(f"[CONTROLLER] Max results: {max_alternatives}")
    print(f"[CONTROLLER] Prompt length: {len(prompt) if prompt else 0}")
    print("=" * 80)

    if not file.filename.lower().endswith(".txt"):
        return {
            "error": True,
            "message": "File must be a .txt file",
            "tokens_input": 0,
            "tokens_output": 0,
            "data": {},
            "method_used": "vector_search" if use_vectors else "traditional",
        }

    try:
        catalog = await openai_service.read_catalog_from_file(file.file)
        print(f"[CONTROLLER] Catalog items loaded: {len(catalog)}")

        if isinstance(search, str):
            search_list = [term.strip() for term in search.split("$$$") if term.strip()]
            print(f"[CONTROLLER] Detectadas {len(search_list)} búsquedas: {search_list}")
        else:
            search_list = search

        if use_vectors:
            print("[CONTROLLER] Usando Vector Search con embeddings")
            result, tokens_input, tokens_output = await openai_service.analyze_catalog_with_vectors(
                search=search_list,
                catalog=catalog,
                max_alternatives=max_alternatives,
                prompt=prompt,
            )
        else:
            print("[CONTROLLER] Usando método tradicional")
            result, tokens_input, tokens_output = await openai_service.analyze_catalog(
                search=search_list,
                catalog=catalog,
                max_alternatives=max_alternatives,
                prompt=prompt,
            )

        print(f"[CONTROLLER] Resultado recibido: {result}")
        print(f"[CONTROLLER] Tokens: input={tokens_input}, output={tokens_output}")

        response = {
            "error": False,
            "message": "",
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "data": result,
            "method_used": "vector_search" if use_vectors else "traditional",
        }

        print(f"[CONTROLLER] Enviando respuesta: {response}")
        return response
    except Exception as exc:
        print(f"[CONTROLLER] ERROR: {str(exc)}")
        return {
            "error": True,
            "message": f"Error analyzing catalog: {str(exc)}",
            "tokens_input": 0,
            "tokens_output": 0,
            "data": {},
            "method_used": "vector_search" if use_vectors else "traditional",
        }

