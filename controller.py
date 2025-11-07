from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from openai_service import OpenAIService
from models import DataAnalyzeRequest

router = APIRouter()
openai_service = OpenAIService()


@router.get("/health")
async def health():
    """
    Health check endpoint para verificar el estado del servicio.
    """
    return {"status": "ok"}


@router.post("/data/analyze")
async def analyze_file(
    file: UploadFile = File(...),
    prompt: str = Form(...)
):
    """
    Endpoint para analizar archivos (PDF, JPG, JPEG, PNG) con OpenAI.
    
    Args:
        file: Archivo a procesar (PDF o imagen)
        prompt: Instrucciones para el análisis con OpenAI
        
    Returns:
        JSON con el resultado del análisis, tokens usados y posibles errores
    """
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    file_ext = None
    for ext in allowed_extensions:
        if file.filename.lower().endswith(ext):
            file_ext = ext
            break
    
    if not file_ext:
        return {
            "error": True, 
            "message": "File must be PDF, JPG, JPEG, or PNG", 
            "tokens_input": 0, 
            "tokens_output": 0, 
            "data": {}
        }
    
    try:
        if file_ext == '.pdf':
            result, tokens_input, tokens_output = await openai_service.process_pdf(file.file, prompt)
        else:
            result, tokens_input, tokens_output = await openai_service.process_image(file.file, prompt)
        
        return {
            "error": False, 
            "message": "", 
            "tokens_input": tokens_input, 
            "tokens_output": tokens_output, 
            "data": result
        }
    except Exception as e:
        return {
            "error": True, 
            "message": str(e), 
            "tokens_input": 0, 
            "tokens_output": 0, 
            "data": {}
        }


@router.post("/catalog/analyze")
async def analyze_catalog_search(
    file: UploadFile = File(...),
    search: str = Form(...),
    prompt: str = Form(""),
    use_vectors: bool = Query(True, description="Usar Vector Search para máxima eficiencia")
):
    """
    Analiza términos de búsqueda contra un catálogo de productos desde archivo .txt,
    utilizando OpenAI GPT-4o-mini para encontrar las coincidencias más relevantes.

    Parámetros:
    - file: Archivo .txt con el catálogo (un producto por línea)
    - search: Término de búsqueda (string)
    - prompt: (Opcional) Instrucciones personalizadas para OpenAI
    - use_vectors: (Query param) Si es True, usa Vector Search con embeddings (RECOMENDADO).
                   Si es False, usa el método tradicional.

    Formato de entrada:
    POST /catalog/analyze?use_vectors=true
    Content-Type: multipart/form-data
    
    file: catalog.txt (archivo con productos, uno por línea)
    search: "GASA HEMOSTATICA DE 20X10"
    prompt: "Instrucciones personalizadas..." (opcional)
    max_results: 3 (opcional)
    
    BENEFICIOS DEL VECTOR SEARCH (use_vectors=true):
    - 90% menos tokens (~400 vs ~3,800)
    - Nombres exactos del catálogo (sin invenciones)
    - Búsquedas más rápidas y precisas
    - Escalable para catálogos grandes (9000+ productos)
    - Caché inteligente de embeddings
    """
    print("=" * 80)
    print(f"[CONTROLLER] Recibido request en /catalog/analyze (vectors={use_vectors})")
    print(f"[CONTROLLER] Archivo: {file.filename}")
    print(f"[CONTROLLER] Search: {search}")
    print(f"[CONTROLLER] Prompt length: {len(prompt) if prompt else 0}")
    print("=" * 80)
    
    # Validar archivo
    if not file.filename.lower().endswith('.txt'):
        return {
            "error": True,
            "message": "File must be a .txt file",
            "tokens_input": 0,
            "tokens_output": 0,
            "data": {},
            "method_used": "vector_search" if use_vectors else "traditional"
        }
    
    try:
        # Leer catálogo desde archivo
        catalog = await openai_service.read_catalog_from_file(file.file)
        print(f"[CONTROLLER] Catalog items loaded: {len(catalog)}")
        
        # Volver a lógica anterior, split por comas
        if isinstance(search, str):
            search_terms = [term.strip() for term in search.split(',') if term.strip()]
            search_list = search_terms
            print(f"[CONTROLLER] Detectadas {len(search_list)} búsquedas: {search_list}")
        else:
            search_list = search
        
        # Elegir método según parámetro use_vectors
        if use_vectors:
            print("[CONTROLLER] Usando Vector Search con embeddings")
            result, tokens_input, tokens_output = await openai_service.analyze_catalog_with_vectors(
                search=search_list,
                catalog=catalog,
                prompt=prompt
            )
        else:
            print("[CONTROLLER] Usando método tradicional")
            result, tokens_input, tokens_output = await openai_service.analyze_catalog(
                search=search_list,
                catalog=catalog,
                prompt=prompt
            )

        print(f"[CONTROLLER] Resultado recibido: {result}")
        print(f"[CONTROLLER] Tokens: input={tokens_input}, output={tokens_output}")

        # Estructurar respuesta
        response = {
            "error": False,
            "message": "",
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "data": result,
            "method_used": "vector_search" if use_vectors else "traditional"
        }
        
        print(f"[CONTROLLER] Enviando respuesta: {response}")
        return response

    except Exception as e:
        print(f"[CONTROLLER] ERROR: {str(e)}")
        return {
            "error": True,
            "message": f"Error analyzing catalog: {str(e)}",
            "tokens_input": 0,
            "tokens_output": 0,
            "data": {},
            "method_used": "vector_search" if use_vectors else "traditional"
        }




