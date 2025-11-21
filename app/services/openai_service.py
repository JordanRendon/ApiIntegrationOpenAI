from openai import OpenAI
from PyPDF2 import PdfReader
from fastapi import HTTPException
from PIL import Image
import os
import base64
import json
import re
import numpy as np
import faiss
from dotenv import load_dotenv
from typing import Union, List, Dict, Any, Tuple
from app.services.vector_cache import VectorCache

load_dotenv()


class OpenAIService:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        
        self.client = OpenAI(api_key=api_key)
        # Modelos optimizados
        self.vision_model = "gpt-4o-mini"  # Para análisis de imágenes/PDFs
        self.embedding_model = "text-embedding-3-small"  # Para búsqueda semántica
        self.temperature = 0.0
        self.max_tokens = 1024
        self.top_p = 0.0
        
        # Sistema de caché vectorial
        self.vector_cache = VectorCache()

    def clean_json_response(self, text: str) -> dict:
        """Limpia respuestas JSON que puedan venir con formato markdown"""
        cleaned = text.strip()
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        if cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        try:
            return json.loads(cleaned)
        except:
            return {"raw_response": cleaned}
    
    def clean_prompt(self, prompt: str) -> str:
        """Limpia el prompt de caracteres problemáticos"""
        if not prompt:
            return ""
        
        # Reemplazar caracteres de escape problemáticos
        cleaned = prompt.replace('\\n', '\n')
        cleaned = cleaned.replace('\\t', '\t')
        cleaned = cleaned.replace('\\r', '\r')
        cleaned = cleaned.replace('\\"', '"')
        cleaned = cleaned.replace("\\'", "'")
        
        # Limpiar caracteres Unicode problemáticos
        cleaned = cleaned.encode('utf-8', errors='ignore').decode('utf-8')
        
        # Remover saltos de línea excesivos
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
        
        return cleaned.strip()

    async def read_catalog_from_file(self, file) -> List[str]:
        """
        Lee un archivo .txt y convierte cada línea en un elemento del catálogo.
        
        Args:
            file: Archivo .txt con productos (uno por línea)
            
        Returns:
            Lista de strings con los productos del catálogo
        """
        try:
            # Leer contenido del archivo
            file.seek(0)
            content = file.read()
            
            # Decodificar contenido (manejar diferentes encodings)
            try:
                text_content = content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text_content = content.decode('latin-1')
                except UnicodeDecodeError:
                    text_content = content.decode('utf-8', errors='ignore')
            
            # Dividir por líneas y limpiar
            lines = text_content.strip().split('\n')
            
            # Filtrar líneas vacías y limpiar espacios
            catalog = []
            for line in lines:
                cleaned_line = line.strip()
                if cleaned_line:  # Solo agregar líneas no vacías
                    catalog.append(cleaned_line)
            
            print(f"[FILE_READER] Archivo leído exitosamente")
            print(f"[FILE_READER] Total líneas procesadas: {len(lines)}")
            print(f"[FILE_READER] Productos válidos: {len(catalog)}")
            
            if len(catalog) == 0:
                raise ValueError("El archivo está vacío o no contiene productos válidos")
            
            # Mostrar algunos ejemplos
            print(f"[FILE_READER] Primeros 3 productos:")
            for i, product in enumerate(catalog[:3]):
                print(f"  {i+1}. {product[:80]}{'...' if len(product) > 80 else ''}")
            
            return catalog
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading catalog file: {str(e)}")

    def pdf_to_image(self, pdf_file):
        """Convierte la primera página del PDF a imagen usando PyMuPDF"""
        try:
            import fitz  # PyMuPDF
            import io
            
            pdf_file.seek(0)
            pdf_bytes = pdf_file.read()
            
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            if pdf_document.page_count == 0:
                raise ValueError("PDF no tiene páginas")
            
            page = pdf_document[0]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            
            img_buffer = io.BytesIO()
            img_buffer.write(pix.tobytes("png"))
            img_buffer.seek(0)
            
            pdf_document.close()
            return img_buffer
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error converting PDF to image: {str(e)}")

    async def process_pdf(self, pdf_file, prompt: str) -> tuple[dict, int, int]:
        """Procesa PDF convirtiéndolo a imagen y analizándolo con Vision"""
        try:
            image_buffer = self.pdf_to_image(pdf_file)
            return await self.process_image(image_buffer, prompt)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

    def encode_image_to_base64(self, image_file) -> str:
        """Convierte imagen a base64 optimizado para OpenAI"""
        image_file.seek(0)
        image = Image.open(image_file)
        
        original_size = image.size
        original_mode = image.mode
        print(f"[IMAGEN] Tamanio original: {original_size[0]}x{original_size[1]} px")
        
        target_size = (1024, 768)
        image = image.resize(target_size, Image.Resampling.LANCZOS)
        
        from io import BytesIO
        buffered = BytesIO()
        
        if original_mode in ('RGBA', 'LA') or (original_mode == 'P' and 'transparency' in image.info):
            image.save(buffered, format="PNG", optimize=True)
            output_format = "PNG"
        else:
            if image.mode != 'RGB':
                image = image.convert('RGB')
            image.save(buffered, format="JPEG", quality=85, optimize=True)
            output_format = "JPEG"
        
        img_bytes = buffered.getvalue()
        print(f"[IMAGEN] Procesada: {target_size[0]}x{target_size[1]} px, {output_format}")
        
        return base64.b64encode(img_bytes).decode('utf-8')
    
    async def process_image(self, image_file, prompt: str) -> tuple[dict, int, int]:
        """Procesa imagen con GPT-4o-mini Vision"""
        try:
            image_file.seek(0)
            temp_image = Image.open(image_file)
            original_mode = temp_image.mode
            image_file.seek(0)
            
            base64_image = self.encode_image_to_base64(image_file)
            
            mime_type = "image/png" if original_mode in ('RGBA', 'LA') or (original_mode == 'P' and 'transparency' in temp_image.info) else "image/jpeg"
            
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {"role": "system", "content": "Extract information from image and return valid JSON."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}}
                        ]
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=self.top_p,
                response_format={"type": "json_object"}
            )
            
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Empty response from model")
            
            result = self.clean_json_response(response.choices[0].message.content)
            tokens_input = response.usage.prompt_tokens
            tokens_output = response.usage.completion_tokens
            
            print(f"[TOKENS] ENTRADA: {tokens_input}, SALIDA: {tokens_output}")
            
            return result, tokens_input, tokens_output
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")

    def analyze_search_intent(self, search: str) -> int:
        """
        Analiza el texto de búsqueda para determinar cuántos productos está buscando el usuario.
        
        Detecta:
        - Conectores múltiples: "y", "o", ",", "también", "además"
        - Múltiples cantidades: "500ml y 187mg", "100g y 50g"
        - Patrones de enumeración: "aceite de 500ml, de 100ml y de 200ml"
        - Productos con múltiples presentaciones: "acido glicolico", "aceite", etc.
        
        Args:
            search: Texto de búsqueda del usuario
            
        Returns:
            Número estimado de productos que el usuario busca (1 a N)
        """
        search_lower = search.lower()
        
        # 1. Detectar conectores múltiples
        connectors = ['\\by\\b', '\\bo\\b', ',', 'tambien', 'también', 'ademas', 'además']
        connector_matches = sum(1 for c in connectors if re.search(c, search_lower))
        
        # 2. Detectar múltiples cantidades/dosis (ej: 500ml, 187mg, 100g, 1kg, 2l)
        quantities = re.findall(r'\d+\s*(?:ml|mg|g|kg|l|cc|oz|lb|cap|tab|comp|sobre|amp)', search_lower)
        unique_quantities = list(set(quantities))  # Eliminar duplicados
        
        # 3. NUEVO: Detectar productos que típicamente tienen múltiples presentaciones
        multi_presentation_products = [
            # Productos farmacéuticos
            'acido glicolico', 'aceite', 'crema', 'gel', 'locion', 'shampoo', 'emulsion',
            'solucion', 'suspension', 'pomada', 'ungüento', 'spray', 'espuma',
            'hialuronato', 'hidratante', 'protector', 'antiseptico', 'desinfectante',
            
            # Dispositivos médicos
            'cateter', 'canula', 'gasa', 'aposito', 'filtro', 'electrodo', 'barrera',
            'adaptador', 'conector', 'tubo', 'sonda', 'aguja', 'jeringa', 'bolsa',
            'bata', 'guante', 'mascarilla', 'protector', 'vendaje', 'sutura',
            
            # Equipos y accesorios
            'detergente', 'indicador', 'dilatador', 'dispositivo', 'boton', 'eliminador',
            'enjuague', 'filtro', 'humidificador', 'monitor', 'sensor', 'cable',
            
            # Productos de limpieza/esterilización
            'detergente', 'enzimatico', 'esterilizante', 'desinfectante', 'limpiador'
        ]
        
        # Verificar si la búsqueda contiene productos de múltiples presentaciones
        has_multi_presentation = any(product in search_lower for product in multi_presentation_products)
        
        # 4. NUEVO: Detectar palabras que indican presentaciones específicas
        presentation_words = [
            'crem', 'emul', 'loc', 'shamp', 'gel', 'sol', 'cap', 'tab', 'comp', 'sobre',
            'spray', 'espuma', 'pomada', 'ungüento', 'suspension', 'jarabe', 'drops',
            'gotas', 'ampolla', 'vial', 'frasco', 'tubo', 'sachet'
        ]
        
        # Contar palabras de presentación en la búsqueda
        presentation_count = sum(1 for word in presentation_words if word in search_lower)
        
        # 5. NUEVO: Detectar si la búsqueda es específica o genérica
        search_words = search_lower.split()
        is_specific_search = len(search_words) >= 3  # 3+ palabras = búsqueda específica
        
        # 6. Lógica de decisión mejorada
        if len(unique_quantities) >= 2:
            # Si hay 2+ cantidades diferentes, probablemente busca múltiples productos
            print(f"[ANALISIS] Detectadas {len(unique_quantities)} cantidades diferentes -> Retornar top {len(unique_quantities)}")
            return len(unique_quantities)
        elif connector_matches >= 1 and len(search_lower.split()) >= 5:
            # Si hay conectores y la búsqueda es larga, probablemente son 2-3 productos
            estimated = min(connector_matches + 1, 3)
            print(f"[ANALISIS] Detectados {connector_matches} conectores -> Retornar top {estimated}")
            return estimated
        elif is_specific_search:
            # Búsqueda específica (3+ palabras): retornar solo el mejor match
            # Ejemplo: "ADAPTADOR LIBRE DE AGUJA", "ACIDO GLICOLICO CREMA"
            print(f"[ANALISIS] Busqueda especifica ({len(search_words)} palabras) -> Retornar top 1")
            return 1
        elif has_multi_presentation and not presentation_count:
            # Producto genérico con múltiples presentaciones
            # Ejemplo: "ADAPTADOR", "ACIDO GLICOLICO", "ACEITE"
            print(f"[ANALISIS] Producto generico con multiples presentaciones -> Retornar top 5")
            return 5
        elif has_multi_presentation and presentation_count >= 1:
            # Producto con presentación específica mencionada
            print(f"[ANALISIS] Producto con presentacion especifica -> Retornar top 2")
            return 2
        else:
            # Búsqueda simple: retornar solo el mejor match
            print(f"[ANALISIS] Busqueda simple -> Retornar top 1")
            return 1

    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Genera embeddings para una lista de textos usando text-embedding-3-small.
        Procesa en lotes para manejar catálogos grandes (9000+ productos).
        
        Args:
            texts: Lista de strings para convertir a embeddings
            
        Returns:
            Array numpy con los embeddings (shape: [len(texts), 1536])
        """
        try:
            print(f"[EMBEDDINGS] Generando embeddings para {len(texts)} textos...")
            
            # Configuración de lotes para evitar límites de OpenAI
            batch_size = 2000  # OpenAI permite hasta 2048 inputs por llamada
            all_embeddings = []
            total_tokens = 0
            
            # Procesar en lotes
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(texts) + batch_size - 1) // batch_size
                
                print(f"[EMBEDDINGS] Procesando lote {batch_num}/{total_batches} ({len(batch)} textos)")
                
                # Validar que los textos no estén vacíos
                valid_batch = []
                for text in batch:
                    if text and text.strip():
                        # Truncar textos muy largos (OpenAI tiene límite de ~8191 tokens)
                        if len(text) > 8000:  # Aproximadamente 8000 caracteres = ~2000 tokens
                            text = text[:8000] + "..."
                        valid_batch.append(text.strip())
                
                if not valid_batch:
                    print(f"[EMBEDDINGS] Lote {batch_num} vacío, saltando...")
                    continue
                
                # Llamada a OpenAI para generar embeddings del lote
                response = self.client.embeddings.create(
                    model=self.embedding_model,
                    input=valid_batch,
                    encoding_format="float"
                )
                
                # Extraer los vectores de embedding del lote
                batch_embeddings = []
                for item in response.data:
                    batch_embeddings.append(item.embedding)
                
                all_embeddings.extend(batch_embeddings)
                total_tokens += response.usage.total_tokens
                
                print(f"[EMBEDDINGS] Lote {batch_num} completado: {len(batch_embeddings)} embeddings")
            
            # Convertir a array numpy
            embeddings_array = np.array(all_embeddings, dtype=np.float32)
            print(f"[EMBEDDINGS] TOTAL: {embeddings_array.shape[0]} embeddings de {embeddings_array.shape[1]} dimensiones")
            
            # Información de tokens y costo total
            cost = (total_tokens / 1_000_000) * 0.020  # $0.020 per 1M tokens para text-embedding-3-small
            print(f"[EMBEDDINGS] Tokens totales: {total_tokens}, Costo: ${cost:.6f} USD")
            
            return embeddings_array
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"[EMBEDDINGS] ERROR COMPLETO:")
            print(error_details)
            raise HTTPException(status_code=500, detail=f"Error generating embeddings: {str(e)}")
    
    def create_faiss_index(self, embeddings: np.ndarray) -> faiss.Index:
        """
        Crea un índice FAISS para búsqueda vectorial eficiente.
        
        Args:
            embeddings: Array numpy con embeddings (shape: [n_items, embedding_dim])
            
        Returns:
            Índice FAISS listo para búsquedas
        """
        try:
            dimension = embeddings.shape[1]  # Dimensión de los embeddings (1536 para text-embedding-3-small)
            n_items = embeddings.shape[0]
            
            print(f"[FAISS] Creando índice para {n_items} items con dimensión {dimension}")
            
            # Crear índice FAISS (IndexFlatIP para similitud coseno)
            index = faiss.IndexFlatIP(dimension)
            
            # Normalizar embeddings para similitud coseno
            faiss.normalize_L2(embeddings)
            
            # Agregar embeddings al índice
            index.add(embeddings)
            
            print(f"[FAISS] Índice creado exitosamente con {index.ntotal} vectores")
            return index
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating FAISS index: {str(e)}")
    
    def extract_medical_specifications(self, search_text: str) -> Dict[str, List[str]]:
        """
        Extrae especificaciones médicas técnicas de un texto de búsqueda.
        
        Args:
            search_text: Texto de búsqueda del usuario
            
        Returns:
            Diccionario con especificaciones encontradas
        """
        search_upper = search_text.upper()
        
        specs = {
            'volume': re.findall(r'\d+\.?\d*\s*ML\b', search_upper),
            'gauge': re.findall(r'\d+G\b', search_upper),
            'length': re.findall(r'\d+\.?\d*\s*(?:CM|MM|INCH|"|\s1/2|\s3/4)\b', search_upper),
            'dose': re.findall(r'\d+\.?\d*\s*MG\b', search_upper),
            'dimensions': re.findall(r'\d+\s*[X*]\s*\d+(?:\s*[X*]\s*\d+)?', search_upper),
            'diameter': re.findall(r'\d+\.?\d*\s*(?:MM|CM)\b', search_upper),
            'french': re.findall(r'\d+\.?\d*\s*FR?\b', search_upper),
            'units': re.findall(r'\d+\.?\d*\s*(?:UI|IU|UNIDADES?)\b', search_upper)
        }
        
        # Limpiar especificaciones vacías
        specs = {k: v for k, v in specs.items() if v}
        
        if specs:
            print(f"[SPEC_EXTRACTOR] Especificaciones encontradas: {specs}")
        
        return specs

    def calculate_specification_bonus(self, product: str, search_specs: Dict[str, List[str]]) -> float:
        """
        Calcula bonus de confidence basado en coincidencias de especificaciones exactas.
        
        Args:
            product: Nombre del producto del catálogo
            search_specs: Especificaciones extraídas de la búsqueda
            
        Returns:
            Bonus de confidence (0.0 a 0.6)
        """
        product_upper = product.upper()
        total_bonus = 0.0
        
        # Volumen exacto (crítico para jeringas, medicamentos)
        if 'volume' in search_specs:
            for vol in search_specs['volume']:
                if vol in product_upper:
                    total_bonus += 0.3
                    print(f"[SPEC_BONUS] Volumen exacto '{vol}' encontrado: +0.3")
                    break
        
        # Calibre exacto (crítico para agujas, catéteres)
        if 'gauge' in search_specs:
            for gauge in search_specs['gauge']:
                if gauge in product_upper:
                    total_bonus += 0.2
                    print(f"[SPEC_BONUS] Calibre exacto '{gauge}' encontrado: +0.2")
                    break
        
        # Dimensiones exactas (crítico para gasas, apósitos)
        if 'dimensions' in search_specs:
            for dim in search_specs['dimensions']:
                # Normalizar formato (X vs *)
                dim_normalized = dim.replace('*', 'X').replace(' ', '')
                product_normalized = product_upper.replace('*', 'X').replace(' ', '')
                if dim_normalized in product_normalized:
                    total_bonus += 0.2
                    print(f"[SPEC_BONUS] Dimensión exacta '{dim}' encontrada: +0.2")
                    break
        
        # Dosis exacta (crítico para medicamentos)
        if 'dose' in search_specs:
            for dose in search_specs['dose']:
                if dose in product_upper:
                    total_bonus += 0.15
                    print(f"[SPEC_BONUS] Dosis exacta '{dose}' encontrada: +0.15")
                    break
        
        # Longitud exacta (importante para catéteres, agujas)
        if 'length' in search_specs:
            for length in search_specs['length']:
                if length in product_upper:
                    total_bonus += 0.1
                    print(f"[SPEC_BONUS] Longitud exacta '{length}' encontrada: +0.1")
                    break
        
        return min(total_bonus, 0.6)  # Máximo bonus de 0.6

    def search_similar_products(self, query_embedding: np.ndarray, catalog_data: Dict[str, Any], 
                              top_k: int = 10, search_text: str = "") -> List[Tuple[str, float, int]]:
        """
        Busca productos similares usando el índice FAISS con re-ranking híbrido.
        Devuelve una lista más larga que top_k para que GPT escoja las alternativas.
        """
        try:
            faiss_index = catalog_data['faiss_index']
            catalog = catalog_data['catalog']
            
            # Normalizar query embedding para similitud coseno
            faiss.normalize_L2(query_embedding)
            
            # Buscar más productos inicialmente para tener opciones (usamos top_k como el número de candidatos a devolver)
            initial_k = min(top_k, len(catalog)) 
            scores, indices = faiss_index.search(query_embedding, initial_k)
            
            # Extraer especificaciones de la búsqueda
            search_specs = self.extract_medical_specifications(search_text)
            
            # Preparar resultados con re-ranking híbrido
            results = []
            for i in range(len(indices[0])):
                idx = indices[0][i]
                base_score = float(scores[0][i])
                product = catalog[idx]
                
                # Calcular bonus por especificaciones exactas
                spec_bonus = self.calculate_specification_bonus(product, search_specs)
                
                # Score final híbrido
                final_score = base_score + spec_bonus
                
                results.append((product, final_score, idx))
            
            # Ordenar por score final (híbrido) y tomar solo los top_k
            results.sort(key=lambda x: x[1], reverse=True)
            final_results = results
            
            print(f"[HYBRID_SEARCH] Encontrados {len(final_results)} productos candidatos para el LLM.")
            for i, (product, score, idx) in enumerate(final_results[:3]):  # Mostrar top 3
                print(f"  {i+1}. {product[:60]}... (score: {score:.4f})")
            
            return final_results
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error searching similar products: {str(e)}")

    def coincide_molecula_y_concentracion(self, search_term: str, producto: str) -> bool:
        """
        Retorna True si las moléculas y concentraciones coinciden sin importar el orden.
        Ejemplo: 'SALMETEROL + FLUTICASONA 25+125MCG' == 'FLUTICASONA+SALMETEROL (125MCG+25MCG)'
        """
        import re
        def extraer_principios(texto):
            texto = texto.lower()
            texto = re.sub(r'[^a-z0-9+]', ' ', texto) # Quita símbolos pero deja +
            partes = [p.strip() for p in texto.split('+') if p.strip()]
            return partes
        def extraer_concentraciones(texto):
            # Busca todas las concentraciones del tipo 25MCG, 125MG, etc.
            return sorted(re.findall(r'\d+\s*[a-z]+', texto.lower()))

        p1 = set(extraer_principios(search_term))
        p2 = set(extraer_principios(producto))
        c1 = set(extraer_concentraciones(search_term))
        c2 = set(extraer_concentraciones(producto))
        # Si ambos conjuntos no son vaciós y coinciden exactamente
        return bool(p1) and bool(p2) and p1 == p2 and c1 == c2

    def es_nombre_igual(self, a: str, b: str) -> bool:
        import re
        limpia = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
        return limpia(a) == limpia(b)

    async def analyze_catalog_with_vectors(
        self,
        search: List[str],
        catalog: List[str],
        prompt: str = None,
        max_alternatives: int = 0
    ) -> tuple[dict, int, int]:
        """
        Analiza catálogo usando Vector Search con embeddings para máxima eficiencia.
        
        VENTAJAS:
        - Reduce tokens de ~3,800 a ~400 (90% menos)
        - Nombres exactos del catálogo (sin invenciones)
        - Búsquedas más rápidas y precisas
        - Escalable para catálogos grandes
        
        FLUJO:
        1. Primera vez: Genera embeddings del catálogo (costo inicial)
        2. Siguientes: Usa embeddings en caché (solo costo de búsqueda)
        3. Busca productos similares con FAISS
        4. Envía solo los top N productos al modelo GPT
        """
        try:
            print("=" * 80)
            print("[VECTOR_SEARCH] Iniciando análisis con sistema vectorial")
            print(f"[VECTOR_SEARCH] Búsquedas: {search}")
            print(f"[VECTOR_SEARCH] Catálogo: {len(catalog)} productos")
            print(f"[VECTOR_SEARCH] Prompt length: {len(prompt) if prompt else 0}")
            print("=" * 80)
            
            # 1. Generar hash del catálogo
            catalog_hash = self.vector_cache.get_catalog_hash(catalog)
            print(f"[VECTOR_SEARCH] Hash del catálogo: {catalog_hash[:8]}...")
            
            # 2. Verificar si el catálogo ya está procesado
            catalog_data = self.vector_cache.get_catalog_data(catalog_hash)
            embedding_tokens = 0
            
            if catalog_data is None:
                # PRIMERA VEZ: Procesar catálogo completo
                print(f"[VECTOR_SEARCH] Procesando catálogo por primera vez...")
                print(f"[VECTOR_SEARCH] Generando embeddings para {len(catalog)} productos...")
                
                # Generar embeddings del catálogo
                catalog_embeddings = self.generate_embeddings(catalog)
                
                # Crear índice FAISS
                faiss_index = self.create_faiss_index(catalog_embeddings)
                
                # Guardar en caché
                self.vector_cache.save_catalog_vectors(
                    catalog_hash, catalog, catalog_embeddings, faiss_index
                )
                
                catalog_data = self.vector_cache.get_catalog_data(catalog_hash)
                
                # Calcular tokens usados para embeddings (aproximado)
                total_chars = sum(len(product) for product in catalog)
                embedding_tokens = int(total_chars / 4)  # Aproximación: 1 token ≈ 4 caracteres
                
                print(f"[VECTOR_SEARCH] Catálogo procesado y guardado en caché")
            else:
                # CATÁLOGO YA PROCESADO: Usar caché
                print(f"[VECTOR_SEARCH] Usando catálogo desde caché vectorial")
                print(f"[VECTOR_SEARCH] Productos en caché: {catalog_data['product_count']}")
            
            max_alternatives_val = max_alternatives if max_alternatives is not None else 0
            candidates_to_fetch = max_alternatives_val + 1
            faiss_fetch_k = max(candidates_to_fetch * 2, 5)

            print(f"[VECTOR_SEARCH] Max alternativas solicitadas: {max_alternatives_val}")
            print(f"[VECTOR_SEARCH] FAISS buscará {faiss_fetch_k} candidatos por término.")
            
            # 4. Procesar cada búsqueda
            all_candidates_by_search_term = {}
            total_search_tokens = 0
            
            for search_term in search:
                print(f"[VECTOR_SEARCH] Procesando búsqueda: '{search_term}'")
                
                # FILTRO PREVIO: buscar coincidencias exactas en TODO el catálogo
                matches_exactos = []
                match_igual = None
                for idx, producto in enumerate(catalog):
                    if self.coincide_molecula_y_concentracion(search_term, producto):
                        matches_exactos.append((producto, 1.0, idx))
                        if self.es_nombre_igual(search_term, producto):
                            match_igual = (producto, 1.0, idx)
                if matches_exactos:
                    # Si existe un match exactamente igual en nombre, ordena la lista con ese primero
                    if match_igual and match_igual in matches_exactos:
                        matches_exactos.remove(match_igual)
                        candidates = [match_igual] + matches_exactos[:(max_alternatives_val or 0)]
                    else:
                        candidates = matches_exactos[:(max_alternatives_val or 0)+1]
                    print(f"[PRE-FILTRO MOL/CONC] Se encontraron {len(matches_exactos)} matches exactos en catálogo para '{search_term}' (match_igual={'sí' if match_igual else 'no'})")
                else:
                    # Vector search solo como fallback si no hay exactos
                    query_embedding_response = self.client.embeddings.create(
                        model=self.embedding_model,
                        input=[search_term],
                        encoding_format="float"
                    )
                    query_embedding = np.array(query_embedding_response.data[0].embedding, dtype=np.float32).reshape(1, -1)
                    total_search_tokens += query_embedding_response.usage.total_tokens
                    similar_products_data = self.search_similar_products(
                        query_embedding=query_embedding,
                        catalog_data=self.vector_cache.get_catalog_data(self.vector_cache.get_catalog_hash(catalog)),
                        top_k=max(((max_alternatives_val or 0)+1)*2, 5),
                        search_text=search_term
                    )
                    candidates = similar_products_data
                    print(f"[VECTOR SEARCH] Usando productos más similares FAISS para '{search_term}'")

                all_candidates_by_search_term[search_term] = candidates
                
                # Preparar el contexto de los productos para el LLM y el prompt final
            products_context_text = ""
            user_prompt = "Analiza los candidatos proporcionados para cada término de búsqueda. "
                
                # Preparar mini-catálogo con solo los productos relevantes
            for search_term, candidates in all_candidates_by_search_term.items():
                user_prompt += f"\n\n--- Término de Búsqueda: {search_term} ---\n"

                # Inyectamos los candidatos en el prompt del usuario como contexto
                context_list = []
                for i, (product, score, index) in enumerate(candidates):
                    context_list.append(f"CANDIDATO {i+1} (CAT-INDEX {index}): {product} (FAISS-Score: {score:.4f})")

                products_context_text += f"\n\n--- Candidatos para '{search_term}' ---\n"
                products_context_text += "\n".join(context_list)
                
            # Preparar prompt personalizado o usar el por defecto
            if prompt:
                user_prompt += f"\n\nInstrucciones adicionales del usuario: {self.clean_prompt(prompt)}"

                system_prompt = f"""
                Eres un especialista en insumos médico-quirúrgicos con profundo conocimiento en dispositivos, materiales hospitalarios y productos farmacéuticos.

                Tu tarea es analizar un término de búsqueda y un conjunto de productos candidatos (provenientes del catálogo) para identificar el producto principal y las posibles alternativas válidas.

                === REGLAS DE ANÁLISIS (CRÍTICAS) ===
                1️⃣ Producto principal:
                - Debe ser el producto más similar o idéntico al término buscado.
                - Coincidencia exacta de moléculas y forma farmacéutica preferida.
                2️⃣ Alternativas válidas:
                - Misma molécula o combinación de principios activos (sin importar el orden).
                - Misma concentración exacta en valores y unidades (25+125MCG = 25MCG+125MCG).
                - Misma forma farmacéutica (tableta, aerosol, cápsula, suspensión, etc.).
                - Solo puede variar el laboratorio o fabricante.
                - Si difiere cualquier valor o unidad → descartar.
                3️⃣ Si no existen alternativas válidas:
                Devuelve solo el producto principal con:
                {{ "mensaje": "No hay alternativas disponibles" }}
                4️⃣ Si el producto principal no está en el catálogo:
                Devuelve:
                {{ "mensaje": "Producto principal no encontrado en catálogo" }}

                === FORMATO JSON OBLIGATORIO ===
                {{
                "matches": [
                    {{
                        "search": "término de búsqueda original",
                        "item": "nombre exacto del producto principal (del catálogo)",
                        "confidence": "valor entre 0.0 y 1.0",
                        "index": "CAT-INDEX del producto principal",
                        "alternatives": [
                            {{
                                "item": "nombre exacto del producto alternativo",
                                "confidence": "valor entre 0.0 y 1.0",
                                "index": "CAT-INDEX del alternativo"
                            }}
                        ]
                    }}
                ]
                }}

                === CONTEXTO DEL CATÁLOGO ===
                {products_context_text}

                === INSTRUCCIONES ADICIONALES ===
                {self.clean_prompt(prompt)}
                """
            else:
                system_prompt = f"""
                Eres un motor de análisis de catálogos...
                # (mantén el prompt anterior si el usuario no pasa prompt personalizado)
                """
            final_system_message = self.clean_prompt(system_prompt + products_context_text) # Inyectamos el contexto al system prompt

                # Llamada al modelo GPT con mini-catálogo
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {"role": "system", "content": final_system_message},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=self.top_p,
                response_format={"type": "json_object"}
            )
                
            if not response.choices or not response.choices[0].message.content:
                    raise ValueError("Empty response from model")
                
            # Procesar resultado
            result = self.clean_json_response(response.choices[0].message.content)
            all_matches = result.get('matches', [])
            
            # Si no hay matches, retornar vacío (el LLM ya debería haber manejado esto)
            if not all_matches:
                return {"matches": []}, total_search_tokens, 0
            
            # Truncar alternatives según max_alternatives solicitado y validar mensajes
            max_alternatives_val = max_alternatives if max_alternatives is not None else 0
            
            # Procesar cada match para validar alternativas y agregar mensajes
            for match in all_matches:
                # Asegurar que alternatives existe y es una lista
                if 'alternatives' not in match:
                    match['alternatives'] = []
                elif not isinstance(match['alternatives'], list):
                    match['alternatives'] = []
                
                # Solo validar mensajes si se solicitó max_alternatives
                if max_alternatives_val > 0:
                    # Truncar alternativas al máximo solicitado
                    alternatives = match['alternatives']
                    num_alternatives = len(alternatives)
                    
                    # Truncar si hay más de las solicitadas
                    if num_alternatives > max_alternatives_val:
                        match['alternatives'] = alternatives[:max_alternatives_val]
                        num_alternatives = max_alternatives_val
                    
                    # Validar y agregar mensajes según corresponda
                    if num_alternatives == 0:
                        # No se encontraron alternativas
                        match['message'] = "No se encontraron alternativas"
                    elif num_alternatives < max_alternatives_val:
                        # Hay algunas alternativas pero no todas las solicitadas
                        match['message'] = "No se encontraron más alternativas"
                    # Si num_alternatives == max_alternatives_val, no agregar mensaje (hay suficientes)
                else:
                    # Si no se solicitó max_alternatives, no agregar mensajes
                    pass
            
            total_search_tokens += response.usage.prompt_tokens + response.usage.completion_tokens             
            
            # 5. Calcular costos y tokens
            embedding_cost = (embedding_tokens / 1_000_000) * 0.020 if embedding_tokens > 0 else 0
            search_cost = (total_search_tokens / 1_000_000) * 0.150  # GPT-4o-mini input cost
            total_cost = embedding_cost + search_cost
            
            print(f"[VECTOR_SEARCH] RESUMEN:")
            print(f"  - Productos encontrados: {len(all_matches)}")
            print(f"  - Tokens embeddings: {embedding_tokens}")
            print(f"  - Tokens búsqueda: {total_search_tokens}")
            print(f"  - Costo total: ${total_cost:.6f} USD")
            print(f"  - Reducción vs tradicional: ~90%")
            
            # 6. Retornar resultado
            return {"matches": all_matches}, total_search_tokens, 0
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"[VECTOR_SEARCH] ERROR COMPLETO:")
            print(error_details)
            raise HTTPException(status_code=500, detail=f"Error analyzing catalog with vectors: {str(e)}\n\nDetalle completo: {error_details}")

    async def analyze_catalog(
        self,
        search: List[str],
        catalog: List[str],
        max_results: int = None,
        prompt: str = None
    ) -> tuple[dict, int, int]:
        """
        Analiza uno o varios términos de búsqueda contra un catálogo usando GPT-4o-mini.
        Permite procesar múltiples búsquedas en una sola llamada (reduciendo costo y latencia).
        """
        try:
            # 1. Usar directamente el array de búsquedas
            search_terms = search
            
            print(f"[BUSQUEDAS] {len(search_terms)} término(s)")
            for i, term in enumerate(search_terms, 1):
                print(f"  {i}. '{term}'")
            print(f"[CATALOGO] {len(catalog)} items")
            print(f"[MODELO] GPT-4o-mini con prompt")

            # 2. Determinar resultados máximos
            if max_results is not None:
                n_results = max_results
                print(f"[CONFIG] max_results especificado: {n_results}")
            else:
                # usa el primero como referencia para calcular n_results
                n_results = self.analyze_search_intent(search_terms[0])

            # 3. Limpiar prompt de caracteres problemáticos
            if prompt:
                original_prompt = prompt
                prompt = self.clean_prompt(prompt)
                print(f"[DEBUG] Prompt limpiado: {len(prompt)} caracteres")
                if len(original_prompt) != len(prompt):
                    print(f"[DEBUG] Prompt cambió de {len(original_prompt)} a {len(prompt)} caracteres")
            
            # 4. Prompt por defecto (si no viene personalizado)
            if not prompt or prompt.strip() == "":
                prompt = """Eres un experto en productos medicos, farmaceuticos y dispositivos hospitalarios.
Analiza cada termino de busqueda y encuentra los productos mas relevantes en el catalogo.

CRITERIOS DE BUSQUEDA (orden de prioridad):
1. Nombre/Tipo de producto (40%)
2. Especificaciones tecnicas (30%)
3. Presentacion (15%)
4. Similitud semantica (15%)

REGLAS IMPORTANTES:
- Las especificaciones numericas son criticas (500ML diferente de 250ML, 16G diferente de 18G).
- Tolera variaciones de formato (10X10CM = 10*10CM = 10CM*10CM).
- Ignora mayusculas/minusculas.
"""

            # 4. Construir catálogo numerado
            catalog_str = "\n".join([f"{i}. {item}" for i, item in enumerate(catalog)])

            # 5. Construir prompt completo
            if len(search_terms) == 1:
                # Búsqueda simple
                user_message = f"""BUSQUEDA: "{search_terms[0]}"

CATALOGO (Total: {len(catalog)} productos):
{catalog_str}

INSTRUCCIONES:
- Retorna SOLO los {n_results} productos mas relevantes
- Calcula un confidence score (0.0 a 1.0) para cada match
- Ordena por relevancia descendente
- Retorna JSON con esta estructura exacta:
{{
    "matches": [
        {{"item": "nombre completo del producto", "confidence": 0.95, "index": 0}},
        ...
    ]
}}"""
            else:
                # Múltiples búsquedas
                user_message = "Analiza los siguientes terminos de busqueda individualmente:\n\n"
                for i, term in enumerate(search_terms, 1):
                    user_message += f"{i}. {term}\n"
                
                user_message += f"\nCATALOGO (Total: {len(catalog)} productos):\n{catalog_str}\n\n"
                user_message += f"INSTRUCCIONES:\n- Retorna SOLO los {n_results} productos mas relevantes para cada busqueda.\n"
                user_message += """- Calcula un confidence score (0.0 a 1.0) por match.
- Ordena por relevancia descendente.
- Devuelve un JSON con esta estructura exacta:
[
  {
    "search": "termino de busqueda",
    "matches": [
      {"item": "nombre del producto", "confidence": 0.95, "index": 0},
      ...
    ]
  }
]"""

            # 6. Llamar al modelo
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un experto en análisis de productos médicos y farmacéuticos. Siempre retornas JSON válido."
                    },
                    {"role": "user", "content": prompt + "\n\n" + user_message}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=self.top_p,
                response_format={"type": "json_object"}
            )

            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Empty response from model")

            result = self.clean_json_response(response.choices[0].message.content)
            
            # Debug: mostrar respuesta de OpenAI
            print(f"[DEBUG] Respuesta de OpenAI: {result}")
            print(f"[DEBUG] Tipo de resultado: {type(result)}")

            # 7. Tokens y costo
            tokens_input = response.usage.prompt_tokens
            tokens_output = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens

            cost_input = (tokens_input / 1_000_000) * 0.150
            cost_output = (tokens_output / 1_000_000) * 0.600
            total_cost = cost_input + cost_output

            print(f"[TOKENS] In: {tokens_input} / Out: {tokens_output} / Total: {total_tokens}")
            print(f"[COSTO] ${total_cost:.6f} USD")

            # Procesar resultado según el tipo de búsqueda
            if len(search_terms) == 1:
                # Búsqueda simple: esperamos {"matches": [...]}
                matches = result.get('matches', [])
                print(f"[RESULTADO] Matches encontrados: {len(matches)}")
                
                if matches:
                    print(f"[TOP MATCH] '{matches[0]['item']}' (confidence: {matches[0].get('confidence', 0)})")
                
                return {"matches": matches}, tokens_input, tokens_output
            
            else:
                # Múltiples búsquedas: esperamos [{"search": "...", "matches": [...]}, ...]
                all_matches = []
                
                if isinstance(result, list):
                    # Formato esperado: lista de objetos con search y matches
                    for search_result in result:
                        if 'matches' in search_result:
                            all_matches.extend(search_result['matches'])
                elif isinstance(result, dict) and 'matches' in result:
                    # Formato alternativo: un solo objeto con matches
                    all_matches = result['matches']
                elif isinstance(result, dict) and 'results' in result:
                    # Formato con 'results': {'results': [{'search': '...', 'matches': [...]}]}
                    for search_result in result['results']:
                        if 'matches' in search_result:
                            all_matches.extend(search_result['matches'])
                else:
                    # Formato inesperado, intentar extraer cualquier matches
                    print(f"[WARNING] Formato de respuesta inesperado: {result}")
                    all_matches = result.get('matches', [])
                
                print(f"[RESULTADO] Total matches encontrados: {len(all_matches)}")
                
                if all_matches:
                    print(f"[TOP MATCH] '{all_matches[0]['item']}' (confidence: {all_matches[0].get('confidence', 0)})")
                
                return {"matches": all_matches}, tokens_input, tokens_output

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error analyzing catalog: {str(e)}")
        
    # openai_service.py (Añadir dentro de la clase OpenAIService)

    def extract_max_alternatives(self, prompt: str) -> int:
        """
        Analiza el prompt del usuario para encontrar peticiones de alternativas.
        Ejemplos: "dame 3 alternativas", "necesito otras 2 opciones", "lista 4 productos similares".
        
        Returns:
            int: Número de alternativas solicitadas (0 si no se encuentra).
        """
        if not prompt:
            return 0
        
        prompt_lower = prompt.lower()
        
        # Patrones comunes para buscar: (\d+|uno|dos|tres|cuatro|cinco) + (alternativa|opción|similar|producto)
        
        # 1. Patrón numérico (ej: "3 alternativas", "2 opciones")
        match_num = re.search(r'(\d+)\s+(?:alternativas?|opciones?|similares?|productos?)', prompt_lower)
        if match_num:
            return int(match_num.group(1))

        # 2. Patrón de palabras (solo los más comunes)
        word_to_num = {'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5}
        for word, num in word_to_num.items():
            if f" {word} " in prompt_lower or prompt_lower.endswith(f" {word}"):
                if any(kw in prompt_lower for kw in ['alternativa', 'opcion', 'similar', 'producto']):
                    print(f"[PROMPT_ANALYSIS] Detectado: '{word}' -> {num} alternativas")
                    return num
        
        return 0
