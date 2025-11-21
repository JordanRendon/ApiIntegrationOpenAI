from pydantic import BaseModel


class DataAnalyzeRequest(BaseModel):
    """
    Modelo para analizar documentos (PDF/Imágenes) con IA.
    """

    prompt: str

