from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import hashlib
import json
import numpy as np
import faiss
from datetime import datetime


class VectorCache:
    """
    Sistema de caché vectorial para búsqueda semántica eficiente.
    Convierte catálogos a embeddings y permite búsquedas rápidas sin reenviar todo el catálogo.
    """
    def __init__(self):
        self.catalogs: Dict[str, Dict[str, Any]] = {}
        self.max_catalogs = 10  # Límite de catálogos en memoria
        self.max_age_hours = 24  # Tiempo máximo de vida
        
    def get_catalog_hash(self, catalog: List[str]) -> str:
        """Genera un hash único para el catálogo"""
        catalog_str = json.dumps(sorted(catalog), ensure_ascii=False)
        return hashlib.md5(catalog_str.encode('utf-8')).hexdigest()
    
    def has_catalog(self, catalog_hash: str) -> bool:
        """Verifica si un catálogo ya está procesado y vigente"""
        if catalog_hash not in self.catalogs:
            return False
            
        # Verificar si no ha expirado
        catalog_data = self.catalogs[catalog_hash]
        age_hours = (datetime.now() - catalog_data['created_at']).total_seconds() / 3600
        
        if age_hours > self.max_age_hours:
            # Catálogo expirado, eliminar
            del self.catalogs[catalog_hash]
            return False
            
        # Actualizar último uso
        catalog_data['last_used'] = datetime.now()
        return True
    
    def save_catalog_vectors(self, catalog_hash: str, catalog: List[str], 
                           embeddings: np.ndarray, faiss_index: faiss.Index):
        """Guarda un catálogo procesado con sus embeddings e índice FAISS"""
        self.catalogs[catalog_hash] = {
            'catalog': catalog,
            'embeddings': embeddings,
            'faiss_index': faiss_index,
            'created_at': datetime.now(),
            'last_used': datetime.now(),
            'product_count': len(catalog)
        }
        
        # Limpiar catálogos antiguos si excedemos el límite
        self._cleanup_old_catalogs()
    
    def get_catalog_data(self, catalog_hash: str) -> Optional[Dict[str, Any]]:
        """Obtiene los datos vectoriales de un catálogo"""
        if self.has_catalog(catalog_hash):
            return self.catalogs[catalog_hash]
        return None
    
    def _cleanup_old_catalogs(self):
        """Limpia catálogos antiguos para mantener el uso de memoria bajo control"""
        if len(self.catalogs) <= self.max_catalogs:
            return
        
        # Ordenar por último uso y eliminar los más antiguos
        sorted_catalogs = sorted(
            self.catalogs.items(),
            key=lambda x: x[1]['last_used']
        )
        
        # Mantener solo los más recientes
        catalogs_to_keep = dict(sorted_catalogs[-self.max_catalogs:])
        self.catalogs = catalogs_to_keep
        
        print(f"[VECTOR_CACHE] Limpieza realizada. Catálogos activos: {len(self.catalogs)}")


# Modelos eliminados: CatalogData y AnalyzeRequest
# Ahora el endpoint /catalog/analyze recibe archivos .txt directamente


class DataAnalyzeRequest(BaseModel):
    """
    Modelo para analizar documentos (PDF/Imágenes) con IA
    """
    prompt: str

