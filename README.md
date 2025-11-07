Medicar AI API

FastAPI application for catalog search, file analysis and data processing using OpenAI GPT-4o-mini.

## 📁 Structure

- `main.py` - FastAPI application with CORS configuration
- `controller.py` - API endpoints (routes)
- `openai_service.py` - OpenAI service integration
- `models.py` - Pydantic models for request/response validation

## 🔌 Endpoints

### GET `/health`
Health check endpoint to verify service status.

**Response:**
```json
{
  "status": "ok"
}
```

### POST `/data/analyze`
Analyze files (PDF, JPG, JPEG, PNG) with OpenAI Vision.

**Parameters:**
- `file` (multipart/form-data): File to process
- `prompt` (form field): Instructions for analysis

**Response:**
```json
{
  "error": false,
  "message": "",
  "tokens_input": 150,
  "tokens_output": 85,
  "data": { /* AI analysis result */ }
}
```

### POST `/catalog/search`
Search and analyze items within a catalog using OpenAI GPT-4o-mini with semantic search.

**Características:**
- 🎯 Búsqueda semántica inteligente
- 🔍 Detecta sinónimos y errores tipográficos
- 📊 Confidence scoring (0.0 a 1.0)
- ⚡ Optimizado para velocidad y costo
- 📝 Prompt opcional (usa uno optimizado por defecto)

**Body (JSON) - Opción 1 (RECOMENDADO - Sin prompt):**
```json
{
  "search": "paracetamol",
  "catalog": [
    "Paracetamol 500mg",
    "Ibuprofeno 400mg",
    "Aspirina 100mg",
    "Acetaminofén 500mg"
  ]
}
```

**Body (JSON) - Opción 2 (Con prompt personalizado):**
```json
{
  "search": "paracetamol",
  "catalog": [
    "Paracetamol 500mg",
    "Ibuprofeno 400mg"
  ],
  "prompt": "Dado el texto del search, identifica todos los strings de catalog cual es el de mayor coincidencia, con su respectivo confidence"
}
```

**Response:**
```json
{
  "error": false,
  "message": "",
  "tokens_input": 145,
  "tokens_output": 78,
  "data": {
    "matches": [
      {
        "item": "Paracetamol 500mg",
        "confidence": 0.95,
        "index": 0,
        "reason": "Coincidencia exacta del término búsqueda"
      },
      {
        "item": "Acetaminofén 500mg",
        "confidence": 0.87,
        "index": 3,
        "reason": "Sinónimo médico de paracetamol"
      }
    ],
    "search_term": "paracetamol",
    "total_items_analyzed": 4,
    "total_matches": 2
  }
}
```

## ⚙️ Configuration

### 🤖 Modelo: GPT-4o-mini

**¿Por qué GPT-4o-mini?**
- ✅ **90-95% precisión** en búsqueda semántica
- ✅ **94% más económico** que GPT-4o
- ✅ **Muy rápido**: 1-2 segundos de respuesta
- ✅ **Confidence scoring confiable**
- ✅ **Detecta sinónimos y errores tipográficos**

**Costos aproximados:**
- Búsqueda en catálogo de 50 items: ~$0.000135 USD
- 10,000 búsquedas: ~$1.35 USD

Para más detalles, ver [MODEL_COMPARISON.md](MODEL_COMPARISON.md)

### Parámetros:
- `model`: gpt-4o-mini
- `temperature`: 0.0 (deterministic responses)
- `max_tokens`: 1024
- `top_p`: 0.0
- `response_format`: json_object

OPENAI_API_KEY=your_api_key_here

Docker:
docker build -t neodrive-ai-api .
docker run -d -p 8001:8000 --name neodrive-ai-api neodrive-ai-api
docker logs -f neodrive-ai-api
docker stop neodrive-ai-api
docker rm neodrive-ai-api

Local:
python main.py

API: http://localhost:8000
Docs: http://localhost:8000/docs

